export function seatKey(side, position) {
  return `${side}:${position}`;
}

export function isSeatTaken(side, position, occupiedSeats) {
  return occupiedSeats.has(seatKey(side, position));
}

export function firstFreePosition(side, occupiedSeats) {
  for (let pos = 1; pos <= 4; pos += 1) {
    if (!isSeatTaken(side, pos, occupiedSeats)) return pos;
  }
  return null;
}

export function sideHasFreeSeats(side, occupiedSeats) {
  return firstFreePosition(side, occupiedSeats) != null;
}

export function occupantName(debate, side, position) {
  const match = (debate?.participants || []).find(
    (p) => p.connected && p.side === side && p.position === position,
  );
  return match?.name || "已占用";
}

export function validateSeatStep({ side, position, occupiedSeats }) {
  if (!sideHasFreeSeats(side, occupiedSeats)) {
    return { ok: false, message: "该辩方四个席位均已占用，请选择另一方。" };
  }
  if (isSeatTaken(side, position, occupiedSeats)) {
    return { ok: false, message: "该席位已被占用，请选择其他席位。" };
  }
  return { ok: true, message: "" };
}
