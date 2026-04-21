"""
Run on the Pi: python calibrate_track.py
Renders the SVG, extracts the bright-pixel center of each gauge track,
and prints new track_points for gauges.yaml.
"""
import numpy as np
import cv2
import cairosvg
import yaml

with open('config/gauges.yaml') as f:
    gauges = yaml.safe_load(f)

svg_cfg = gauges['svg']
png = cairosvg.svg2png(url=svg_cfg['path'],
                       output_width=svg_cfg['native_width'],
                       output_height=svg_cfg['native_height'])
img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)

# Sample 8 y-positions matching the tick marks
y_ticks = [571, 513, 454, 394, 334, 278, 221, 164]

for gauge_name, x_range in [('tachometer', (100, 600)), ('speedometer', (1360, 1860))]:
    print(f'\n{gauge_name} track_points:')
    pts = []
    for y in y_ticks:
        row = img[y, x_range[0]:x_range[1]]
        # Convert to HSV and find bright/saturated pixels (the colored track)
        hsv = cv2.cvtColor(row.reshape(1, -1, 3), cv2.COLOR_BGR2HSV)
        sat = hsv[0, :, 1]
        val = hsv[0, :, 2]
        bright = (sat > 80) & (val > 80)
        xs = np.where(bright)[0]
        if len(xs) > 0:
            cx = int(np.median(xs)) + x_range[0]
        else:
            cx = (x_range[0] + x_range[1]) // 2
        pts.append([cx, y])
        print(f'  y={y}: x={cx}  (bright px: {len(xs)})')
    print(f'  yaml: {pts}')
