"""
AUR package querying.

Specifically as it relates to what the current system state is
"""


def options(parser):
    """Get query options."""
    group = parser.add_argument_group("Query options")
    group.add_argument('-g', "--gone",
                       help="""specifying this option will interrogate package
information and indicate packages that are not tracked via repositories or the
AUR (orphaned).""",
                       action="store_true")
