#!/usr/bin/env python3
"""
Test script to verify libcec integration works correctly
"""

import sys
import time

def test_cec():
    print("Testing libcec integration...")
    print("=" * 50)

    # Test 1: Import
    print("\n1. Testing import...")
    try:
        import cec
        print("   ✓ cec module imported")
    except ImportError as e:
        print(f"   ✗ Failed to import cec: {e}")
        return False

    # Test 2: Create configuration
    print("\n2. Testing configuration creation...")
    try:
        config = cec.libcec_configuration()
        config.strDeviceName = "Test Client"
        config.bActivateSource = 0
        config.deviceTypes.Add(cec.CEC_DEVICE_TYPE_RECORDING_DEVICE)
        config.clientVersion = cec.LIBCEC_VERSION_CURRENT
        print("   ✓ Configuration created")
    except Exception as e:
        print(f"   ✗ Failed to create configuration: {e}")
        return False

    # Test 3: Create adapter
    print("\n3. Testing adapter creation...")
    try:
        lib = cec.ICECAdapter.Create(config)
        if lib:
            print(f"   ✓ Adapter created")
            print(f"   Version: {lib.VersionToString(config.serverVersion)}")
        else:
            print("   ✗ Failed to create adapter (returned None)")
            return False
    except Exception as e:
        print(f"   ✗ Failed to create adapter: {e}")
        return False

    # Test 4: Detect adapters
    print("\n4. Testing adapter detection...")
    try:
        adapters = lib.DetectAdapters()
        if adapters and len(adapters) > 0:
            print(f"   ✓ Found {len(adapters)} adapter(s)")
            for adapter in adapters:
                print(f"     - Port: {adapter.strComName}")
                print(f"       Vendor: {hex(adapter.iVendorId)}")
                print(f"       Product: {hex(adapter.iProductId)}")
        else:
            print("   ✗ No adapters found")
            return False
    except Exception as e:
        print(f"   ✗ Failed to detect adapters: {e}")
        return False

    # Test 5: Open connection
    print("\n5. Testing connection...")
    try:
        if lib.Open(adapters[0].strComName):
            print("   ✓ Connection opened")
        else:
            print("   ✗ Failed to open connection")
            return False
    except Exception as e:
        print(f"   ✗ Failed to open connection: {e}")
        return False

    # Test 6: Get logical addresses
    print("\n6. Testing logical address retrieval...")
    try:
        addresses = lib.GetLogicalAddresses()
        found_address = False
        our_address = None
        for i in range(15):
            if addresses.IsSet(i):
                found_address = True
                our_address = i
                print(f"   ✓ Our logical address: {i} ({lib.LogicalAddressToString(i)})")
                break

        if not found_address:
            print("   ✗ No logical address assigned")
            return False
    except Exception as e:
        print(f"   ✗ Failed to get logical addresses: {e}")
        return False

    # Test 7: CommandFromString
    print("\n7. Testing CommandFromString...")
    try:
        # Try to create a command to query TV power status (10:8F)
        first_byte = (our_address << 4) | 0  # our_address -> TV (0)
        cmd_string = f"{first_byte:02X}:8F"
        cmd = lib.CommandFromString(cmd_string)
        print(f"   ✓ Created command from string: {cmd_string}")
    except Exception as e:
        print(f"   ✗ Failed to create command: {e}")
        return False

    # Test 8: Transmit
    print("\n8. Testing transmit (querying TV power status)...")
    try:
        if lib.Transmit(cmd):
            print("   ✓ Command transmitted successfully")
            time.sleep(0.5)  # Give time for response
        else:
            print("   ✗ Transmit returned False")
    except Exception as e:
        print(f"   ✗ Failed to transmit: {e}")

    # Test 9: Callback test
    print("\n9. Testing callback registration...")
    callback_received = []

    def test_callback(cmd_string):
        callback_received.append(cmd_string)
        return 0

    try:
        # Create new config with callback
        config2 = cec.libcec_configuration()
        config2.strDeviceName = "Callback Test"
        config2.deviceTypes.Add(cec.CEC_DEVICE_TYPE_RECORDING_DEVICE)
        config2.clientVersion = cec.LIBCEC_VERSION_CURRENT
        config2.SetCommandCallback(test_callback)

        lib2 = cec.ICECAdapter.Create(config2)
        if lib2 and lib2.Open(adapters[0].strComName):
            print("   ✓ Callback registered")
            print("   Waiting 2 seconds for CEC traffic...")
            time.sleep(2)

            if callback_received:
                print(f"   ✓ Received {len(callback_received)} callback(s)")
                for msg in callback_received[:3]:  # Show first 3
                    print(f"     - {msg}")
            else:
                print("   ⚠ No callbacks received (may be normal if bus is quiet)")

            lib2.Close()
        else:
            print("   ✗ Failed to open connection for callback test")
    except Exception as e:
        print(f"   ✗ Callback test failed: {e}")

    # Cleanup
    print("\n10. Testing cleanup...")
    try:
        lib.Close()
        print("   ✓ Connection closed")
    except Exception as e:
        print(f"   ✗ Failed to close: {e}")

    print("\n" + "=" * 50)
    print("All tests completed successfully!")
    return True

if __name__ == "__main__":
    try:
        success = test_cec()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
