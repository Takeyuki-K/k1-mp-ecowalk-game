"""State replay plus optional genuine ROS 2 bag (no ROS required for local play)."""
import json
from pathlib import Path

class Recorder:
    def __init__(self, directory, metadata, rosbag=False):
        self.path = Path(directory)
        self.path.mkdir(parents=True, exist_ok=False)
        (self.path/'metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2))
        self.file = (self.path/'states.jsonl').open('w')
        self.writer = None
        if rosbag:
            try:
                import rosbag2_py
                from rclpy.serialization import serialize_message
                from std_msgs.msg import String
                self.serialize, self.String = serialize_message, String
                self.writer = rosbag2_py.SequentialWriter()
                self.writer.open(rosbag2_py.StorageOptions(uri=str(self.path/'rosbag'),storage_id='sqlite3'),
                                 rosbag2_py.ConverterOptions('',''))
                self.writer.create_topic(rosbag2_py.TopicMetadata(id=0,name='/k1_game/frame',type='std_msgs/msg/String',serialization_format='cdr'))
            except Exception:
                self.file.close()
                raise

    def append(self, row):
        line = json.dumps(row, separators=(',',':'), allow_nan=False)
        self.file.write(line+'\n')
        if self.writer:
            self.writer.write('/k1_game/frame',self.serialize(self.String(data=line)),int(round(row['t']*1e9)))

    def close(self, result):
        self.file.close()
        self.writer = None
        (self.path/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))


def rows(directory):
    path = Path(directory)
    if path.is_dir() and (path/'states.jsonl').exists():
        with (path/'states.jsonl').open() as f:
            for line in f:
                yield json.loads(line)
    else:
        import rosbag2_py
        from rclpy.serialization import deserialize_message
        from std_msgs.msg import String
        reader = rosbag2_py.SequentialReader()
        reader.open(rosbag2_py.StorageOptions(uri=str(path),storage_id='sqlite3'),rosbag2_py.ConverterOptions('',''))
        while reader.has_next():
            topic, data, _ = reader.read_next()
            if topic == '/k1_game/frame':
                yield json.loads(deserialize_message(data,String).data)
