"""Feature ordering shared by the geometry experiment and its article renderer."""
import numpy as np


def geometry_features(geometry, duty):
    """Return the fixed 15-term quadratic basis without importing a PDE solver."""
    normalized = np.array([
        float(geometry['heater_width_um']) / 12,
        float(geometry['heater_pitch_um']) / 40,
        float(geometry['anchor_width_um']) / 12,
        duty / .5,
    ])
    quadratic = [
        normalized[i] * normalized[j]
        for i in range(4)
        for j in range(i, 4)
    ]
    return np.r_[1, normalized, quadratic]
