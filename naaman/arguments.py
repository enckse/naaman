"""Argument processing/handling for naaman."""


def _multi_args(value):
    """Handle specifying a multi-count arg."""
    val = False
    multi = False
    triple = False
    if value and value > 0:
        val = True
        if value > 1:
            multi = True
        if value > 2:
            triple = True
    return val, multi, triple


def manual_args(args):
    """Manual arg parse."""
    r, fr, ffr = _multi_args(args.refresh)
    args.refresh = r
    args.force_refresh = fr
    args.force_force_refresh = ffr
    args.info, args.info_verbose, _ = _multi_args(args.info)
