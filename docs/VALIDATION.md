# Validation

Environment: Linux x86_64, Python 3.12, MuJoCo 3.15.0, NumPy 2.3.5, PyTorch 2.14.1; all simulation and policy computation on CPU. Mesa EGL rendering. This is not a measurement of the user's PC or real robot.

- Unit/API tests: energy units, goal dwell and stopped mode, collision episodes, battery swap arithmetic, failed-run score, NaN rejection, server score recalculation, stage-filtered online leaderboard, JSONL state roundtrip, image cache URL route.
- Actual v5.6.3 Stage 1: command 0.9m/s, stop requested after x>19.25m; finished in 27.4s, 3301.02J / 0.91695Wh, 120.475W mean, no collision. Score 2325.03. 8h projection 963.8Wh without auxiliary load. No battery capacity assumed.
- Actual Stage 2: three physical obstacle geoms present even after Stage 1 in the same process; driving straight into the central obstacle records collisions and ultimately falls. A failure correctly receives zero score. This smoke case intentionally does not avoid obstacles; it is not a successful Stage 2 route demonstration.
- Actual game worker: software rendered frame generated, recording produced and read back, Stage 2 -> Stage 1 restart completed.
- First-person and third-person frames inspected; first-person faces forward past the head and third-person shows the robot.
- ROS 2 libraries unavailable here: actual rosbag2 writer/reader execution is unverified. Optional code uses Jazzy's SequentialWriter/SequentialReader APIs and is documented for local testing.
- Ranking HTTP submission/retrieval tested locally. Internet hosting, HTTPS and multi-user load not deployed/tested.
- No upstream tracked files changed. No model weights or mocap assets copied into this game repository.

Reproduce the physics smoke test after setup:

```bash
python scripts/smoke.py
```

Run results: [smoke-results.json](smoke-results.json). Timing and power can vary with dependency versions; compare games under the same pinned upstream sources and software environment.

## v0.2 UI and streaming update

- Python tests: 10 passed, including MJPEG content framing and goal-overlay telemetry (NumPy state is converted to JSON-compatible bool).
- JavaScript: input mapping assertions and jsdom interaction tests passed (title/stage selection, Shift at 4.0m/s, joystick mode switch, latched emergency brake, goal waiting/progress and finished-result dialog).
- Real MuJoCo: independent physics/render threads generated frames and switched Stage 2 -> Stage 1 cleanly; both threads shut down. Software Mesa rendering measured about 4.7-7.8fps here; physics remained at real-time factor 1.0 in the idle check. These values are environment-specific, not a claim of 30/60fps. Shadow/reflection rendering disabled.
- Full Chromium screenshot testing was unavailable because the browser binary download failed. The DOM interaction test does not verify visual layout in a real browser.
- Existing score, stage geometry and policy weights are unchanged. Goals expose region presence and 1-second stop-hold progress to the UI.

Optional UI checks (test-only dependency, not needed to play):

```bash
npm install --prefix /tmp/k1-ui-check jsdom
NODE_PATH=/tmp/k1-ui-check/node_modules node tests/test_ui.cjs
node tests/test_controls.cjs
```

## Enclosed courses and minimap update

- Python tests: 11 passed, including Stage 3 goal completion, S-curve boundary checks, legacy ranking database migration and Stage 3 submission/filtering.
- JavaScript input and jsdom UI interaction checks passed, including Stage 3 selection and minimap drawing with course telemetry.
- Actual MuJoCo: Stage 2 has 4 enclosing wall geoms and Stage 3 has 66 wall geoms in both walking and running models. Robot/wall contacts verified in each model; both stages stepped and rendered at 1280×720 under EGL. Wall contact names participate in the same collision meter as obstacles.
- No full Stage 3 driving route or real-browser layout test was performed.
- Course geometry is shared by simulation, boundary detection, recordings and the minimap. Updated rules separate old-course ranking records without deleting them.

## v0.3 persistent ranking and replay

- Stage 2 orange obstacles now attach alternately to left/right walls, each leaving a 2m opening. Rules version 3 separates the changed course's scores.
- 15 Python tests pass: local finished-record registration, DB persistence/idempotent replay additions, authenticated remote replay retrieval, invalid replay validation and wall attachment geometry added to existing coverage.
- jsdom UI checks pass for replay HUD, disabled driving controls and suppression of the result dialog during replay, alongside previous goal/input checks. JavaScript syntax and input tests pass.
- Actual CPU MuJoCo: recorded Stage 2 motion, loaded its bundle, sought to the exact recorded state, rendered 1280×720, and ran 2× replay through automatic end pause. An older obstacle layout supplied in metadata was reconstructed correctly.
- Internet deployment and real-browser visual layout remain unverified.

## Rear third-person camera and license inventory

- Third-person view now looks along the robot heading from directly behind. Target height 0.85m, distance 4m, elevation -12 degrees keeps the complete standing robot in the 1280×720 frame.
- Actual MuJoCo EGL frame visually inspected: head, arms and feet visible from the rear. Camera world position and forward direction checked at yaw 0 and pi/2. First-person settings unchanged.
- JavaScript input mapping checks and Python compilation passed. Full pytest suite was not rerun in this refreshed runtime because pytest installation was unavailable.
- Added THIRD_PARTY_LICENSES.md with checked primary-source links for direct integration/reference repositories, upstream model/motion origins, runtime libraries, optional ROS support and test tools. This is not an exhaustive transitive-dependency SBOM.
