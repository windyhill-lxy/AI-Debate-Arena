import assert from "node:assert/strict";
import { citationTokenForArgumentId } from "./argumentCitation.js";

assert.equal(citationTokenForArgumentId("AFF-1"), "[AFF1]");
assert.equal(citationTokenForArgumentId("NEG-12"), "[NEG12]");
assert.equal(citationTokenForArgumentId("AFF1"), "[AFF1]");
assert.equal(citationTokenForArgumentId("  NEG-3  "), "[NEG3]");
assert.equal(citationTokenForArgumentId(""), "");
