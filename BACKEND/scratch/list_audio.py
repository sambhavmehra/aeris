import pyaudio
pa = pyaudio.PyAudio()
print("Available Output Devices:")
for i in range(pa.get_device_count()):
    info = pa.get_device_info_by_index(i)
    if info["maxOutputChannels"] > 0:
        print(f"Index {i}: {info['name']} (Channels: {info['maxOutputChannels']}, Host API: {info['hostApi']}, Default Sample Rate: {info['defaultSampleRate']})")
