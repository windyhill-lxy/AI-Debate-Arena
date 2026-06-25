import { test, expect } from "@playwright/test";

const apiURL = process.env.PLAYWRIGHT_API_URL || "http://127.0.0.1:9000";

async function visibleBoxes(locator) {
  const handles = await locator.elementHandles();
  const boxes = [];
  for (const handle of handles) {
    const box = await handle.boundingBox();
    if (box && box.width > 1 && box.height > 1) boxes.push(box);
  }
  return boxes;
}

function overlapArea(a, b) {
  const x = Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x));
  const y = Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y));
  return x * y;
}

function maxOverlapRatio(boxes) {
  let max = 0;
  for (let i = 0; i < boxes.length; i += 1) {
    for (let j = i + 1; j < boxes.length; j += 1) {
      const area = overlapArea(boxes[i], boxes[j]);
      const smaller = Math.min(boxes[i].width * boxes[i].height, boxes[j].width * boxes[j].height);
      if (smaller > 0) max = Math.max(max, area / smaller);
    }
  }
  return max;
}

function zoomFromTransform(transform) {
  if (!transform || transform === "none") return 1;
  const match = transform.match(/matrix\(([^)]+)\)/);
  if (!match) return 1;
  return Number(match[1].split(",")[0]) || 1;
}

test.describe("辩论室 E2E", () => {
  test.beforeEach(async ({ request }, testInfo) => {
    if (testInfo.title.includes("本地演示")) return;
    const health = await request.get(`${apiURL}/health`).catch(() => null);
    test.skip(!health?.ok(), "后端未启动（需 http://127.0.0.1:9000）");
  });

  test("创建房间并看到首条流式或已发布发言", async ({ page }) => {
    await page.goto("/");

    const quickDemo = page.getByTestId("schedule-quick_demo");
    if (await quickDemo.isVisible()) {
      await quickDemo.click();
    }

    await page.getByTestId("home-enter-room").click();
    await page.waitForURL(/\/room\/(?!demo)/, { timeout: 30_000 });

    const board = page.getByTestId("debate-message-board");
    await expect(board).toBeVisible();

    const streaming = page.getByTestId("debate-streaming");
    const published = page.locator(".message-board .message .md-body");

    await expect(streaming.or(published.first())).toBeVisible({ timeout: 90_000 });

    const hasStream = await streaming.isVisible().catch(() => false);
    if (hasStream) {
      await expect(streaming.locator(".md-body")).not.toBeEmpty();
    } else {
      await expect(published.first()).not.toBeEmpty();
    }
  });

  test("本地演示的流程图展示判断分叉且论据库显示标题和内容", async ({ page }) => {
    await page.goto("/room/demo");

    await page.getByTitle("LangGraph 工作流").click();
    await expect(page.getByTestId("rf__controls")).toBeVisible();
    await expect(page.getByTestId("rf__minimap")).toHaveCount(0);
    await expect(page.locator(".workflow-flow-node")).toHaveCount(12);
    await expect(page.locator(".workflow-flow-node--decision").first()).toContainText("内容合规?");
    await expect(page.locator(".workflow-flow")).toContainText("通过");
    await expect(page.locator(".workflow-flow")).toContainText("退回");
    await expect(page.locator(".workflow-flow")).toContainText("重写");
    await expect(page.locator(".workflow-flow-node__spinner")).toBeVisible();
    await expect(page.locator(".workflow-flow-node").first()).toHaveAttribute("title", /用户|联机席位|提交/);
    await expect(page.locator(".workflow-flow")).not.toContainText("大模型判断");
    await expect(page.locator(".workflow-flow")).not.toContainText("赛制环节推进");

    await page.locator("button[title='论据库']").first().click();
    await expect(page.locator(".argument-bank-side.affirmative .argument-bank-item")).toHaveCount(10);
    await expect(page.locator(".argument-bank-side.negative .argument-bank-item")).toHaveCount(10);
    const firstArgument = page.locator(".argument-bank-item").first();
    await expect(firstArgument.locator(".argument-bank-item__title")).toContainText("AI作业批改订正率提升");
    await expect(firstArgument.locator(".argument-bank-item__content")).toContainText("学生错题订正率提升近30%");
  });

  test("本地演示主舞台统一显示席位称谓而非 AI 人格名", async ({ page }) => {
    await page.goto("/room/demo");

    await page.evaluate(() => {
      window.dispatchEvent(
        new CustomEvent("debate-demo-inject-message", {
          detail: {
            id: "seat-label-test",
            speaker_id: "aff_2",
            speaker_name: "澜汐",
            side: "affirmative",
            phase: "rebuttal",
            segment_label: "正方二辩驳论",
            content: "我作为正方二辩，引用 [AFF-2] 继续推进论证。",
            sources: [],
          },
        }),
      );
    });

    const message = page.locator(".message").filter({ hasText: "正方二辩驳论" }).last();
    await expect(message.locator(".message-head strong")).toHaveText("正方二辩");
    await expect(message.locator(".message-head strong")).not.toContainText("澜汐");
  });

  test("本地演示引用编号保持编号显示并可打开论据详情", async ({ page }) => {
    await page.goto("/room/demo");

    await page.evaluate(() => {
      window.dispatchEvent(
        new CustomEvent("debate-demo-inject-message", {
          detail: {
            id: "cite-test",
            speaker_id: "aff_1",
            speaker_name: "云汐",
            side: "affirmative",
            phase: "opening_statement",
            segment_label: "正方一辩立论",
            content: "我方先引用即时反馈材料 [AFF-1]，再说明它如何支撑学习效率。",
            sources: [],
          },
        }),
      );
    });

    const citation = page.getByRole("button", { name: "[AFF-1]" }).first();
    await expect(citation).toBeVisible();
    await citation.click();
    await expect(page.locator(".citation-detail-panel")).toBeVisible();
    await expect(page.locator(".citation-detail-panel")).toContainText("AI作业批改订正率提升");
    await expect(page.locator(".citation-detail-panel")).toContainText("学生错题订正率提升近30%");
  });

  test("本地演示底部状态明确显示当前节点、调用对象和进度", async ({ page }) => {
    await page.goto("/room/demo");

    const dock = page.locator(".debate-dock");
    await expect(dock).toBeVisible();
    await expect(dock).toContainText("当前节点", { timeout: 8_000 });
    await expect(dock).toContainText("调用");
    await expect(dock).not.toContainText("下一位辩手");
    await expect(dock).not.toContainText("流程推进");
    await expect(page.locator(".debate-progress__mini-track")).toBeVisible();
  });

  test("本地演示流程图大图位于最上层且节点不互相遮挡", async ({ page }) => {
    await page.goto("/room/demo");
    await page.getByTitle("LangGraph 工作流").click();
    await page.getByTitle("打开大图").click();

    const modal = page.locator(".workflow-modal");
    await expect(modal).toBeVisible();

    const modalBox = await modal.boundingBox();
    const dockBox = await page.locator(".debate-dock").boundingBox();
    expect(modalBox).toBeTruthy();
    expect(dockBox).toBeTruthy();
    expect(modalBox.y + modalBox.height).toBeGreaterThan(dockBox.y);

    const topElementClass = await page.evaluate(() => {
      const el = document.elementFromPoint(window.innerWidth / 2, window.innerHeight - 24);
      return el?.closest(".workflow-modal, .debate-dock")?.className || "";
    });
    expect(topElementClass).toContain("workflow-modal");

    const nodeBoxes = await visibleBoxes(page.locator(".workflow-modal .workflow-flow-node"));
    expect(nodeBoxes.length).toBe(12);
    expect(maxOverlapRatio(nodeBoxes)).toBeLessThan(0.02);
    await expect(page.locator(".workflow-modal .workflow-flow-node--decision")).toHaveCount(3);
    await expect(page.locator(".workflow-modal .workflow-flow-node__spinner")).toBeVisible();
    await expect(page.locator(".workflow-modal .workflow-flow")).not.toContainText("赛制环节推进");
  });

  test("本地演示流程图缩放按钮会改变视口比例", async ({ page }) => {
    await page.goto("/room/demo");
    await page.getByTitle("LangGraph 工作流").click();
    await page.getByTitle("打开大图").click();

    const viewport = page.locator(".workflow-modal .react-flow__viewport");
    await expect(viewport).toBeVisible();
    const before = await viewport.evaluate((el) => getComputedStyle(el).transform);

    await page.locator(".workflow-modal .react-flow__controls-zoomin").click();
    await page.waitForTimeout(250);

    const after = await viewport.evaluate((el) => getComputedStyle(el).transform);
    expect(after).not.toBe(before);
  });

  test("本地演示流程图支持滚轮缩放且不会自动缩回", async ({ page }) => {
    await page.goto("/room/demo");
    await page.getByTitle("LangGraph 工作流").click();
    await page.getByTitle("打开大图").click();

    const flow = page.locator(".workflow-modal .workflow-flow");
    const viewport = page.locator(".workflow-modal .react-flow__viewport");
    await expect(viewport).toBeVisible();

    const before = zoomFromTransform(await viewport.evaluate((el) => getComputedStyle(el).transform));
    const box = await flow.boundingBox();
    expect(box).toBeTruthy();
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.wheel(0, -900);
    await page.waitForTimeout(250);

    const wheelZoom = zoomFromTransform(await viewport.evaluate((el) => getComputedStyle(el).transform));
    expect(wheelZoom).toBeGreaterThan(before + 0.05);

    await page.waitForTimeout(900);
    const afterWait = zoomFromTransform(await viewport.evaluate((el) => getComputedStyle(el).transform));
    expect(afterWait).toBeGreaterThanOrEqual(wheelZoom - 0.01);
  });

  test("本地演示论据库长文本不会超出卡片边框", async ({ page }) => {
    await page.goto("/room/demo");
    await page.getByTitle("论据库").click();

    const item = page.locator(".argument-bank-item").first();
    await expect(item).toBeVisible();
    await item.evaluate((el) => {
      const title = el.querySelector(".argument-bank-item__title");
      const body = el.querySelector(".argument-bank-item__content .md-body");
      const source = el.querySelector(".argument-bank-item__source");
      const longText = "超长连续文本".repeat(80);
      if (title) title.textContent = longText;
      if (body) body.textContent = longText;
      if (source) source.textContent = `来源：${longText}`;
    });

    const overflow = await item.evaluate((el) => {
      const targets = [
        el,
        ...el.querySelectorAll(".argument-bank-item__title, .argument-bank-item__content, .argument-bank-item__content *, .argument-bank-item__source"),
      ];
      return targets
        .map((target) => ({
          className: target.className || target.tagName,
          scrollWidth: target.scrollWidth,
          clientWidth: target.clientWidth,
        }))
        .filter((entry) => entry.scrollWidth > entry.clientWidth + 1);
    });
    expect(overflow).toEqual([]);
  });

  test("本地演示右侧浮层不会遮住左侧导航栏", async ({ page }) => {
    await page.goto("/room/demo");
    await page.getByTitle("队内讨论").click();

    const panelBox = await page.locator(".right-sidebar.is-expanded .sidebar-panel-container").boundingBox();
    const leftRailBox = await page.locator(".left-sidebar .sidebar-dock").boundingBox();
    expect(panelBox).toBeTruthy();
    expect(leftRailBox).toBeTruthy();
    expect(panelBox.x).toBeGreaterThan(leftRailBox.x + leftRailBox.width + 8);
  });

  test("本地演示未处理页面错误会弹出错误窗口", async ({ page }) => {
    await page.goto("/room/demo");

    await page.evaluate(() => {
      window.dispatchEvent(
        new ErrorEvent("error", {
          message: "测试页面错误",
          error: new Error("测试页面错误"),
        }),
      );
    });

    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("页面运行错误");
    await expect(dialog).toContainText("测试页面错误");
  });

  test("创建房间失败会弹出错误窗口", async ({ page }) => {
    await page.route("**/api/debates", async (route) => {
      if (route.request().method() !== "POST") {
        await route.fallback();
        return;
      }
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          error: {
            message: "服务器内部错误，请查看日志",
            code: "internal_error",
            status: 500,
            request_id: "test-request-id",
          },
        }),
      });
    });

    await page.goto("/solo");
    await page.getByRole("button", { name: /5\s*确认进入/ }).click();
    await page.getByTestId("home-enter-room").click();

    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("创建房间失败");
    await expect(dialog).toContainText("服务器内部错误");
    await expect(dialog).toContainText("test-request-id");
  });
});
