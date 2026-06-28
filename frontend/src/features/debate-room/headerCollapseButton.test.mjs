import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "../../..");
const source = readFileSync(resolve(root, "src/features/debate-room/components/DebateCenterStage.jsx"), "utf8");

const marker = 'className="export-md-btn export-md-btn--icon"';
const start = source.indexOf(marker);
assert.ok(start > 0, "header collapse control should use the icon button class");
const button = source.slice(start, source.indexOf("</button>", start));

assert.match(button, /<Maximize2 size=\{15\}/, "collapsed state should render an expand icon");
assert.match(button, /<Minimize2 size=\{15\}/, "expanded state should render a collapse icon");
assert.doesNotMatch(button, />\s*\{headerCollapsed \? "展开" : "收起"\}/, "button body should not use text labels");
assert.match(button, /aria-label=\{headerCollapsed \? "展开上方信息" : "收起上方信息"\}/, "accessible labels should remain");
