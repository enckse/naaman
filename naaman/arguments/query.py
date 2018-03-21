def options(parser):
    """Get query options."""
    group = parser.add_argument_group("Query options")
    group.add_argument('-g', "--gone",
                       help="""specifying this option will check for packages
installed from the AUR but are no longer in the AUR.""",
                       action="store_true")
