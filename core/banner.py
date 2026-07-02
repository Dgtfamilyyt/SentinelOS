from core.version import VERSION, AUTHOR

def show_banner():

    print("=" * 55)
    print("🛡️  Sentinel OS")
    print(f"Version       : {VERSION}")
    print(f"Administrator : {AUTHOR}")
    print("Status        : ONLINE")
    print("=" * 55)
    print("Commands")
    print("  /clear   Clear conversation")
    print("  exit     Quit Sentinel")
    print("=" * 55)