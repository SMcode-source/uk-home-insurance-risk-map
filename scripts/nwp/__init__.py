"""A global shallow-water dynamical core, and what it says about the
limits of weather forecasting.

The package exists to answer one question with a measurement rather than
an assertion: how long can a forecast of the atmosphere be useful?  See
scripts/nwp/shallow_water.py for what the equations are and what they
are not, and scripts/nwp/predictability.py for the experiment.
"""

from .spectral import GRAVITY, OMEGA, RADIUS, Sphere          # noqa: F401
from .shallow_water import (ShallowWater, state_from_wind,     # noqa: F401
                            williamson_case2, williamson_case6)
