# ecowalk-drive!! — K1 EcoWalk Game

v5.6.3のK1 MP EcoWalkをCPU MuJoCoでテレオペし、ゴールまでの推定消費エネルギーを競うゲーム。Ubuntu 24.04 / Python 3.12を推奨。GPU不要（描画にはMesa/OpenGLが必要）。Gazeboへの移植は含みません。

既存の `k1-mp-ecowalk-public` と `k1-mp-ecowalk-teleop` は別の依存チェックアウトとして読み込むだけです。本リポジトリから変更しません。対象コミットは `backend.py` と `scripts/setup.sh` に固定しています。

## 起動

```bash
git clone https://github.com/Takeyuki-K/k1-mp-ecowalk-game.git
cd k1-mp-ecowalk-game
sudo apt install python3-venv libgl1-mesa-dri libegl1 libosmesa6
bash scripts/setup.sh
source .venv/bin/activate
MUJOCO_GL=egl k1-game
```

ブラウザで http://localhost:8090 を開きます。タイトルメニューからステージ1・2を選択。プレイ画面はブラウザの表示領域いっぱいに配置し、全画面ボタン（またはF11）も利用できます。ランキング・操作説明は上部ボタンから開きます。privateのteleopリポジトリをcloneできるGitHub認証が必要です。Mesa EGLが使えない環境では `MUJOCO_GL=osmesa` を使用してください。CPUが遅い場合は実時間より遅くなりますが、採点はシミュレーション時間です。torchはCPU版をインストールします。ROS 2なしでも遊べます。

### 操作方式

- **キー操作**：W/↑を押し続けて前進、A/Dまたは←/→で旋回。離すと停止。Shift＋前進で4.0m/s。速度±ボタンまたは「ゆっくり」「歩行」「走行」で通常速度を変更。Space停止、B急停止、C視点切替。
- **画面ジョイスティック**：操作方式を切り替え、パッドをドラッグ。上が前進、左右が旋回。離すと停止。teleopパッケージと同様、縦軸を非線形（gamma=1.7）にして歩行速度を選びやすくしています。
- **USBゲームパッド**：ジョイスティックモードで「USBゲームパッドを使う」を有効化。標準マッピングの左スティック、A停止、B急停止。接続後に一度スティックを中央へ戻してから操作。非標準マッピングは画面パッドを使用してください。
- ダイアログ表示・操作方式切替・フォーカス喪失時は停止指令。通信が0.5秒途絶えると停止。後退・横移動はありません。

### 描画の滑らかさ

MuJoCoの計算も描画も自分のPCで実行し、localhost経由でブラウザへ表示。従来の画像ポーリング（ブラウザ約4fps）をMJPEG連続配信へ変更。標準画質は1280×720・JPEG品質90。標準30fps、最大60fpsまで設定可能です。描画とJPEG処理は専用スレッドで行い、物理計算のロックを占有しません。配信は最新フレームを優先し、古い画像をためません。

```bash
MUJOCO_GL=egl k1-game --render-fps 60
# Mesa EGLで映らない環境
MUJOCO_GL=osmesa k1-game --render-fps 30
```

影と反射を省いて描画負荷を軽減。AMDなどの内蔵GPUを使えるUbuntuデスクトップでは `unset LIBGL_ALWAYS_SOFTWARE` として、ソフトウェア描画を強制しないでください。EGLが使えない場合は `MUJOCO_GL=glfw`（デスクトップ環境が必要）も試せます。OSMesaはCPUソフトウェア描画のフォールバックです。

画面下に実測fpsとシミュレーションの実時間比を表示。数値はPC性能に依存し、60fpsを保証しません。物理・方策は50Hzです。消費電力を測るゲームなので、描画設定を変えても採点に用いる時間・積算方式は変えません。

ゴール範囲内では「停止判定まち…」と判定進捗を重ねて表示。完走すると「ゴール！！」、スコア、消費Wh・平均W・時間・衝突回数・8時間予測を表示し、シミュレーションを停止します。再挑戦・ステージ選択・ランキング送信ができます。

## ステージと採点

- Stage 1：開始位置から20m、障害物なし。
- Stage 2：開始位置から10m。固定箱3個を避けます。位置と寸法は `rules.py`。
- ゴール中心±0.75m（前後）・±1m（左右）内で、立位モード、水平速度<0.08m/s、角速度<0.08rad/sを1秒維持して完走。
- 転倒、範囲外、300秒経過は失敗（0点）。再挑戦は新しい記録。両ステージは個別採点。
- スコア = max(0, 10000 / (1 + E[J]/1000) − 250 × 衝突回数)。同じ衝突回数なら総消費エネルギーが小さいほど高得点。平均Wは別表示。
- 衝突は物理ステップで取得し、20ms区間に一度でも接触した障害物を集約。同一障害物への連続接触は1回、0.3秒を超えて離れて再接触すると再減点。床接触は減点しません。頭・腕は上流モデルの設定どおり非衝突です。

## 電力と8時間予測

物理ステップごとの実際の制御入力・関節状態から、23モーター合計 `P = Σ(τ²/Km² + max(τ q̇, 0))` を積算。Kmは上流比較コードと同じ仮定（4.0、足首roll/腕は2.2）。回生なし。脚だけの上流 `/k1/status` 電力値とは一致しません。モデル推定であり実機電力ではありません。

総消費：Wh = J/3600。平均電力：W = J/秒。8時間のエネルギー：Wh = 平均W × 8。補機電力を設定すれば加算。バッテリーを満充電で開始し、交換回数 = max(0, ceil(8時間Wh / 有効容量Wh) − 1)。同じステージを連続反復、休憩やバッテリー交換の時間を除く単純予測です。

```bash
# 実際に使用するK1バッテリー容量を設定（数値は例でありK1仕様ではない）
k1-game --battery-wh 400 --usable-fraction 0.8 --auxiliary-w 20
```

K1の確実な容量仕様を確認できなかったため、未設定時は交換回数を未算出と表示します。現在の[ROBOTIS公式資料](https://ai.robotis.com/ai_sapiens/introduction_ai_sapiens.html)はK0の46.8V/9Ahを記載していますが、K1同等とは断定せず、自動採用していません。

## 記録と再生

ステージ開始時から `runs/<UUID>/` にmetadata、50Hzの状態・指令・電力・接触・採点JSONL、結果JSONを自動保存。物理は5ms、状態再生は20ms。再生は保存済み状態を直接戻すので、指令の再積分による軌道のずれを避けます。同じコミット・MuJoCo版で使ってください。実時間速度の再生です。

```bash
k1-game --replay runs/<UUID>
```

ROS 2 Jazzy環境では実際のrosbag2も記録できます。ROSをsourceし、`rosbag2_py`, `rclpy`, `std_msgs`をPythonからimportできる必要があります（venvは `python3 -m venv --system-site-packages .venv` で作成）。ゲームが開始した時点でwriterを開き、終了時に閉じます。ROS依存がなければ明示的に失敗します。

```bash
source /opt/ros/jazzy/setup.bash
k1-game --rosbag
ros2 bag info runs/<UUID>/rosbag
k1-game --replay runs/<UUID>/rosbag --stage 1
```

bagトピック `/k1_game/frame`（std_msgs/String）に完全なMuJoCo状態・指令・電力・接触・スコアを格納。`ros2 bag play`はこのトピックを再配信できます。見た目の再生は上の `--replay`。既存teleopの `/joint_states` や `/odom` をこのゲームが配信する構成ではありません。

## 個別プレイとオンラインランキング

各人はローカルで独立プレイ。結果は明示的な操作で共通ランキングAPIへ送信。ステージ別、スコア降順。サーバーはクライアントのスコアを受け取らず、エネルギーと衝突回数から再計算します。物理検証や不正対策はなく、信頼できる招待者の自己申告ランキングです。

```bash
export K1_RANKING_TOKEN='<24文字以上の共有シークレット>'
k1-ranking --host 127.0.0.1 --port 8091
python scripts/submit.py runs/<UUID> --url http://localhost:8091 --player 'player1' --include-replay
curl -H "Authorization: Bearer $K1_RANKING_TOKEN" http://localhost:8091/ranking/1
```

外部の人が使う場合は自分のサーバー上でHTTPSリバースプロキシの背後に配置。サーバーコードは同梱していますがオンライン公開はしていません。ゲーム操作APIはローカルだけにbind。共有tokenはソースに保存しません。`--include-replay`で再生データも収集可能（1送信32MiBまで）。結果送信は自動ではありません。`k1-game --ranking-url https://<server>` を指定すると、画面から名前を入力して結果送信・ステージ別ランキング確認ができます。共有tokenはゲーム起動前に環境変数へ設定します。

## 検証

```bash
python -m pytest tests -q
node tests/test_controls.cjs  # Nodeがある場合：入力マッピング検証
```

採点・単位・停止判定・接触回数・不正な数値を検証。CPU上の実ポリシー検証結果は `docs/smoke-results.json` と `docs/VALIDATION.md`。ROS 2 bag実行とユーザーのPC上の実時間性能は別途確認が必要です。

## ライセンス

本ゲームコード：Apache-2.0。発案・仕様：Takeyuki-K、実装：OpenAI Codex。依存のコード・モデル・参照軌道は各リポジトリのLICENSE/NOTICE/THIRD_PARTY_LICENSESに従います。モデルや動作データは本リポジトリへ再配布しません。ROBOTIS公認ではなくシミュレーション専用です。
