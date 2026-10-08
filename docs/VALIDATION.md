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
