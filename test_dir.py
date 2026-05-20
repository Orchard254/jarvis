import uiautomation as auto

def test():
    attrs = dir(auto)
    
    print("Methods containing 'Walk':")
    print([a for a in attrs if "Walk" in a])
    
    print("\nMethods containing 'Root':")
    print([a for a in attrs if "Root" in a])
    
    print("\nMethods containing 'Tree':")
    print([a for a in attrs if "Tree" in a])

if __name__ == "__main__":
    test()
