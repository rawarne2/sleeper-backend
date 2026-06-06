from services.valuations import registry
from services.valuations.sources.ktc import KtcSource
from services.valuations.sources.fantasycalc import FantasyCalcSource
from services.valuations.sources.sleeper_proj import SleeperProjectionsSource


def register_defaults() -> None:
    registry.register("ktc", KtcSource)
    registry.register("fantasycalc", FantasyCalcSource)
    registry.register("sleeper_proj", SleeperProjectionsSource)


register_defaults()
