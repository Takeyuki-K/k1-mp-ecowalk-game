# 利用・参照したリポジトリとライセンス

確認日：2026-10-08。本ゲーム自身は Apache-2.0（[LICENSE](LICENSE)、[NOTICE](NOTICE)）。以下は本ゲームの直接依存、実装の参照元、および依存先を通して利用するモデル・動作データの出典です。各リンクはライセンスの一次資料です。ゲームリポジトリには依存リポジトリのモデル・学習済み重み・元の動作データをコピーしていません。setup は別チェックアウトを作成します。

## 直接利用・実装参照

| リポジトリ | 利用・参照内容 | ライセンス・確認元 |
|---|---|---|
| [Takeyuki-K/k1-mp-ecowalk-public](https://github.com/Takeyuki-K/k1-mp-ecowalk-public) | v5.6.3 の歩行・走行環境、方策、状態・電力モデル。コミット `04b1c0fded94dcde76411e6bd9d914a56d41102a` 固定 | コード・方策：Apache-2.0。参照動作データには別条件あり。[LICENSE](https://github.com/Takeyuki-K/k1-mp-ecowalk-public/blob/04b1c0fded94dcde76411e6bd9d914a56d41102a/LICENSE)、[NOTICE](https://github.com/Takeyuki-K/k1-mp-ecowalk-public/blob/04b1c0fded94dcde76411e6bd9d914a56d41102a/NOTICE)、[第三者ライセンス](https://github.com/Takeyuki-K/k1-mp-ecowalk-public/blob/04b1c0fded94dcde76411e6bd9d914a56d41102a/THIRD_PARTY_LICENSES.md) |
| [Takeyuki-K/k1-mp-ecowalk-teleop](https://github.com/Takeyuki-K/k1-mp-ecowalk-teleop) | EcoWalk56Sim、停止・旋回・モード切替。ジョイスティックの非線形速度特性を参照してブラウザ側を実装。コミット `a5ea3dbf4f97501c18ff090f86ff4cd413f6aaea` 固定 | [Apache-2.0 / LICENSE](https://github.com/Takeyuki-K/k1-mp-ecowalk-teleop/blob/a5ea3dbf4f97501c18ff090f86ff4cd413f6aaea/LICENSE) |

ステージ、ブラウザUI、ミニマップ、ランキング、状態記録・アップロード・再生はこのゲーム用に実装しています。これらの実装元として別のゲーム・UIテンプレートのリポジトリは使用していません。

## 依存先を通して利用するモデル・動作データ

| 出典リポジトリ | 関係 | ライセンス・確認元 |
|---|---|---|
| [ROBOTIS-GIT/ai_sapiens](https://github.com/ROBOTIS-GIT/ai_sapiens) | EcoWalkに含まれるK1のモデル・メッシュの出典。上流固定コミット `bdc40f126c4a1551422dce44dce144974f7a2f2b` | [Apache-2.0 / LICENSE](https://github.com/ROBOTIS-GIT/ai_sapiens/blob/bdc40f126c4a1551422dce44dce144974f7a2f2b/LICENSE)。モデル変更の記録はEcoWalk側の `ai_sapiens/NOTICE_MODIFICATIONS.md` |
| [BMClab/BMC](https://github.com/BMClab/BMC) | 人の歩行データ `walk2.trc` と、EcoWalk側で変換した歩行参照軌道の出典。`50a05aebcc814e5341860f1b270652e3ea590d20` | 非ソフトウェア：CC BY 4.0、コード：MIT。[READMEのLicense](https://github.com/BMClab/BMC/blob/50a05aebcc814e5341860f1b270652e3ea590d20/README.md)、[LICENSE.txt](https://github.com/BMClab/BMC/blob/50a05aebcc814e5341860f1b270652e3ea590d20/LICENSE.txt)。著者：Marcos Duarte、Renato Naville Watanabe。[DOI](https://doi.org/10.5281/zenodo.4599319)。変換内容・帰属表示はEcoWalkのNOTICEに記載 |
| [una-dinosauria/cmu-mocap](https://github.com/una-dinosauria/cmu-mocap) / CMU Graphics Lab | EcoWalk走行参照軌道の元データ・BVH変換の出典。`09a07f54f3bbb58797325f009282d0b2048a2871` | 研究・商用利用を許可し、CMUとBVH変換者B. Hahneによる追加の使用制限なし。標準のApache/MIT表記ではない。[READMEFIRSTのUSAGE RIGHTS](https://github.com/una-dinosauria/cmu-mocap/blob/09a07f54f3bbb58797325f009282d0b2048a2871/READMEFIRST.txt)。CMUとNSF EIA-0196217への謝辞が求められており、EcoWalk NOTICEに掲載 |

BNR（Bandai Namco Research）やKITのデータは、このゲームの実装・依存資料で使用を確認していません。過去の別実験で扱ったデータと混同しないでください。

## 実行ライブラリ・任意機能・検証ツール

| リポジトリ | 用途 | ライセンス一次資料 |
|---|---|---|
| [google-deepmind/mujoco](https://github.com/google-deepmind/mujoco) | 物理・描画・カメラ | [Apache-2.0](https://github.com/google-deepmind/mujoco/blob/main/LICENSE) |
| [pytorch/pytorch](https://github.com/pytorch/pytorch) | EcoWalk方策のCPU推論 | [BSD系（本体BSD-3-Clause、同梱コードの表示も含む）](https://github.com/pytorch/pytorch/blob/main/LICENSE) |
| [numpy/numpy](https://github.com/numpy/numpy) | 配列・状態処理 | [BSD-3-Clause](https://github.com/numpy/numpy/blob/main/LICENSE.txt) |
| [python-pillow/Pillow](https://github.com/python-pillow/Pillow) | JPEG画像生成 | [MIT-CMU](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| [ros2/rosbag2](https://github.com/ros2/rosbag2) | `--rosbag` 時のみ記録・読込 | [Apache-2.0](https://github.com/ros2/rosbag2/blob/rolling/LICENSE) |
| [ros2/rclpy](https://github.com/ros2/rclpy) | ROSメッセージ直列化（任意） | [Apache-2.0](https://github.com/ros2/rclpy/blob/rolling/LICENSE) |
| [ros2/common_interfaces](https://github.com/ros2/common_interfaces) | std_msgs/String（任意） | [std_msgs/package.xml：Apache-2.0](https://github.com/ros2/common_interfaces/blob/rolling/std_msgs/package.xml) |
| [pytest-dev/pytest](https://github.com/pytest-dev/pytest) | Pythonテストのみ | [MIT](https://github.com/pytest-dev/pytest/blob/main/LICENSE) |
| [jsdom/jsdom](https://github.com/jsdom/jsdom) | 任意のDOMテストのみ。ゲーム配信には含まない | [MIT](https://github.com/jsdom/jsdom/blob/main/LICENSE.txt) |

これは直接依存と主要な出典の一覧であり、pip/ROS/OSが導入する推移的依存の全件SBOMではありません。ライブラリのバイナリやDockerイメージまで再配布する場合は、実際に同梱する各バージョンのLICENSE・NOTICE・追加ライセンスも確認・保持してください。

## 公開・再配布時の扱い

- Apache-2.0のコード・モデルを再配布する場合はライセンス、帰属表示、関係するNOTICEを保持し、変更箇所の表示も保持します。
- 歩行参照データとその派生物はCC BY 4.0の対象です。Apache-2.0へ一括して置き換えず、著者・出典・ライセンス・変更内容を示します。
- CMUデータはREADMEFIRSTの利用条件と謝辞を保持します。
- ゲームの名称・画面・READMEはROBOTIS公認を示すものではありません。
- 現行の別チェックアウト方式でも、依存先のLICENSE・NOTICEを削除しないでください。
