import uiautomation as auto
import inspect

def test():
    print("Signature for WalkTree:")
    print(inspect.signature(auto.WalkTree))
    
    print("\nSignature for WalkControl:")
    print(inspect.signature(auto.WalkControl))

if __name__ == "__main__":
    test()
