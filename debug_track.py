"""Run on Pi: python debug_track.py  → saves debug_track.png"""
import numpy as np, cv2, cairosvg, yaml

with open('config/gauges.yaml') as f:
    g = yaml.safe_load(f)

svg = g['svg']
png = cairosvg.svg2png(url=svg['path'], output_width=svg['native_width'], output_height=svg['native_height'])
img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)

for name, color in [('tachometer', (0,255,255)), ('speedometer', (0,0,255))]:
    pts = g[name]['track_points']
    for i, (x, y) in enumerate(pts):
        cv2.circle(img, (x, y), 12, color, -1)
        cv2.putText(img, str(i), (x-5, y+5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,0), 1)

cv2.imwrite('debug_track.png', img)
print('Saved debug_track.png')
