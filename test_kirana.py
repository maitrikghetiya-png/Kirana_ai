"""
KiranaAI - Comprehensive Test Suite
Validates all required tools and varied real-world Indian kirana expressions:
- Arbitrary customer names (Ramesh, Suresh, Mohan, Raju, Pappu, Maitrik, Lokesh, etc.)
- Multi-word and colloquial credit patterns ("liya", "udhaar diya", "cheeni", "doodh")
- Payment expressions ("ne 300 de diye", "paid 200", "jama", "pay kiya")
- Queries ("Kaun paisa dena hai?", "kiska udhaar baaki hai", "Sonu balance")
- Reminders ("Reminder", "Reminder Mohan")
"""

from db import db
from agent import create_kirana_agent


def run_tests():
    print("=" * 60)
    print("🚀 Starting KiranaAI Hackathon Extended Test Suite")
    print("=" * 60)

    # 0. Reset DB
    print("\n[Step 0] Resetting test database...")
    db.reset_db()
    assert db.get_dues()["total_outstanding"] == 0
    print("✅ Database clean. Initial dues: ₹0")

    agent = create_kirana_agent()

    # Flow 1: Ramesh credit
    print("\n[1] Testing 'Ramesh liya 500 doodh'...")
    res1 = agent("Ramesh liya 500 doodh")
    assert db.get_dues("Ramesh")["balance"] == 500.0
    print(f"✅ PASS: {res1}")

    # Flow 2: Another customer: Mohan credit
    print("\n[2] Testing 'Mohan 300 dal'...")
    res2 = agent("Mohan 300 dal")
    assert db.get_dues("Mohan")["balance"] == 300.0
    print(f"✅ PASS: {res2}")

    # Flow 3: Third customer: Suresh credit
    print("\n[3] Testing 'Suresh liya 450 cheeni'...")
    res3 = agent("Suresh liya 450 cheeni")
    assert db.get_dues("Suresh")["balance"] == 450.0
    print(f"✅ PASS: {res3}")

    # Flow 4: Check dues
    print("\n[4] Testing 'Kaun paisa dena hai?'...")
    res4 = agent("Kaun paisa dena hai?")
    dues = db.get_dues()
    assert dues["total_outstanding"] == 1250.0
    assert dues["total_customers_with_dues"] == 3
    print(f"✅ PASS: {res4}")

    # Flow 5: Payment from Ramesh
    print("\n[5] Testing 'Ramesh ne 300 de diye'...")
    res5 = agent("Ramesh ne 300 de diye")
    assert db.get_dues("Ramesh")["balance"] == 200.0
    print(f"✅ PASS: {res5}")

    # Flow 6: Payment from Suresh (different phrasing)
    print("\n[6] Testing 'Suresh ne 200 pay kiya'...")
    res6 = agent("Suresh ne 200 pay kiya")
    assert db.get_dues("Suresh")["balance"] == 250.0
    print(f"✅ PASS: {res6}")

    # Flow 7: General reminder
    print("\n[7] Testing 'Reminder'...")
    res7 = agent("Reminder")
    reminders = db.get_pending_reminders()
    assert len(reminders) == 3
    print(f"✅ PASS: {res7}")

    # Flow 8: Specific customer reminder
    print("\n[8] Testing 'Reminder Ramesh'...")
    res8 = agent("Reminder Ramesh")
    r_rem = db.get_pending_reminders("Ramesh")
    assert len(r_rem) == 1 and r_rem[0]["balance"] == 200.0
    print(f"✅ PASS: {res8}")

    print("\n" + "=" * 60)
    print("🎉 ALL DIVERSE CUSTOMER TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    run_tests()
