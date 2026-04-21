"""Run on Pi: python calibrate_track2.py"""
import numpy as np, cv2, cairosvg, yaml

with open('config/gauges.yaml') as f:
    g = yaml.safe_load(f)

svg = g['svg']
png = cairosvg.svg2png(url=svg['path'], output_width=svg['native_width'], output_height=svg['native_height'])
img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)

# Convert to grayscale brightness
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

y_ticks = [571, 513, 454, 394, 334, 278, 221, 164]

for gauge_name, x_lo, x_hi in [('tachometer', 50, 700), ('speedometer', 1260, 1910)]:
    print(f'\n{gauge_name}:')
    pts = []
    for y in y_ticks:
        row = gray[y, x_lo:x_hi].astype(float)
        # Find peaks (bright lines forming the channel)
        threshold = row.max() * 0.5
        bright = np.where(row > threshold)[0]
        if len(bright) >= 2:
            # Find leftmost and rightmost cluster
            left_peak  = int(np.median(bright[bright < bright.mean()])) + x_lo
            right_peak = int(np.median(bright[bright >= bright.mean()])) + x_lo
            center = (left_peak + right_peak) // 2
            width = right_peak - left_peak
        elif len(bright) > 0:
            center = int(np.median(bright)) + x_lo
            left_peak = right_peak = center
            width = 0
        else:
            center = (x_lo + x_hi) // 2
            left_peak = right_peak = center
            width = 0
        pts.append([center, y])
        print(f'  y={y}: left={left_peak} right={right_peak} center={center} width={width}px')
    print(f'  track_points: {pts}')
