import uiautomation as auto

def test():
    win = auto.GetRootControl()
    
    print("Testing WalkTree with no kwargs:")
    try:
        count = 0
        for control, depth in auto.WalkTree(win):
            count += 1
            if count > 5:
                break
        print("WalkTree succeeded!")
    except Exception as e:
        print(f"WalkTree failed: {e}")
        
    print("\nTesting WalkControl with no kwargs:")
    try:
        count = 0
        for control, depth in auto.WalkControl(win):
            count += 1
            if count > 5:
                break
        print("WalkControl succeeded!")
    except Exception as e:
        print(f"WalkControl failed: {e}")

if __name__ == "__main__":
    test()
