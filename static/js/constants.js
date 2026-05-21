// Pylos shared constants for the client.
const NUM_LEVELS = 4;
const INITIAL_MARBLES = 15;
const SLOT_SPACING = 1.2;          // distance between adjacent slot centers (units)
const MARBLE_RADIUS = 0.5;         // radius of a marble
const LEVEL_RISE = 0.85;           // y-distance between levels
const PLATE_THICKNESS = 0.2;

function levelSize(lv) { return NUM_LEVELS - lv; }

// Slot world-space center given level/row/col.
// Levels are vertically offset and shifted by 0.5*SLOT_SPACING per level to
// sit on top of 2×2 supporters.
function slotCenter(lv, r, c) {
  const s = levelSize(lv);
  const offset = (s - 1) / 2;             // center the layer
  const x = (c - offset) * SLOT_SPACING;
  const z = (r - offset) * SLOT_SPACING;
  const y = PLATE_THICKNESS + MARBLE_RADIUS + lv * LEVEL_RISE;
  return { x, y, z };
}
