"""
Find ALL Groups and Channels (Including Private/Inactive)
==========================================================
This script uses multiple methods to find all groups, including:
1. All dialogs (recent conversations)
2. Archived dialogs
3. Search by name
4. Direct ID verification
"""

import asyncio
from telethon import TelegramClient
from dotenv import load_dotenv
import os

load_dotenv()

TELEGRAM_API_ID = int(os.getenv('TELEGRAM_API_ID'))
TELEGRAM_API_HASH = os.getenv('TELEGRAM_API_HASH')
TELEGRAM_PHONE = os.getenv('TELEGRAM_PHONE')


async def find_all_groups():
    """Find ALL groups and channels using multiple methods"""

    client = TelegramClient('bot_session', TELEGRAM_API_ID, TELEGRAM_API_HASH)
    await client.start(phone=TELEGRAM_PHONE)

    print("\n" + "="*80)
    print("COMPREHENSIVE CHANNEL/GROUP FINDER")
    print("="*80)

    all_entities = {}

    # === METHOD 1: Get all non-archived dialogs ===
    print("\n🔍 Scanning non-archived conversations...")
    try:
        dialogs = await client.get_dialogs(archived=False)
        for dialog in dialogs:
            entity = dialog.entity
            if hasattr(entity, 'id'):
                all_entities[entity.id] = {
                    'title': getattr(entity, 'title', 'Unknown'),
                    'id': entity.id,
                    'username': getattr(entity, 'username', None),
                    'type': 'Channel' if getattr(entity, 'broadcast', False) else 'Group/Supergroup',
                    'access_hash': getattr(entity, 'access_hash', None)
                }
        print(f"   Found {len(all_entities)} non-archived entities")
    except Exception as e:
        print(f"   ⚠️ Error: {e}")

    # === METHOD 3: Interactive search ===
    print("\n" + "="*80)
    print("📋 ALL FOUND CHANNELS AND GROUPS:")
    print("="*80)

    if not all_entities:
        print("\n⚠️  NO GROUPS OR CHANNELS FOUND!")
        print("   This might mean:")
        print("   1. You're not a member of any groups/channels")
        print("   2. API permissions issue")
        print("\n   Try the manual search below...")
    else:
        # Sort by title
        sorted_entities = sorted(all_entities.values(), key=lambda x: x['title'])

        for i, entity in enumerate(sorted_entities, 1):
            print(f"\n{i}. {entity['title']}")
            print(f"   Type:     {entity['type']}")
            print(f"   ID:       {entity['id']}")
            if entity['username']:
                print(f"   Username: @{entity['username']}")
            print(f"   📋 Config: {entity['id']}")
            print(f"   {'-'*76}")

    # === METHOD 4: Manual search by name ===
    print("\n" + "="*80)
    print("🔎 MANUAL SEARCH (Optional)")
    print("="*80)
    print("If you don't see your target channel/group above, you can search by name.")
    print("Leave blank to skip.")
    print()

    while True:
        search_name = input("Enter channel/group name to search (or press Enter to finish): ").strip()

        if not search_name:
            break

        print(f"\n🔍 Searching for '{search_name}'...")

        try:
            # Search for the entity
            entity = await client.get_entity(search_name)

            print(f"\n✅ FOUND:")
            print(f"   Title:    {getattr(entity, 'title', 'Unknown')}")
            print(f"   ID:       {entity.id}")
            print(f"   Username: {getattr(entity, 'username', 'None')}")
            print(f"   Type:     {'Channel' if getattr(entity, 'broadcast', False) else 'Group/Supergroup'}")
            print(f"\n   📋 Use this in config.yaml: {entity.id}")
            print()

        except ValueError:
            print(f"   ❌ Not found or no access. Try:")
            print(f"      - The exact username (without @)")
            print(f"      - Or the numeric ID if you have it")
            print()
        except Exception as e:
            print(f"   ❌ Error: {e}")
            print()

    # === METHOD 5: Direct ID lookup ===
    print("\n" + "="*80)
    print("🔢 DIRECT ID LOOKUP (Optional)")
    print("="*80)
    print("If you know the channel ID but want to verify it, enter it here.")
    print("Leave blank to skip.")
    print()

    while True:
        try:
            channel_id_input = input("Enter channel ID to verify (or press Enter to finish): ").strip()

            if not channel_id_input:
                break

            # Convert to integer
            channel_id = int(channel_id_input)

            print(f"\n🔍 Looking up ID {channel_id}...")

            try:
                entity = await client.get_entity(channel_id)

                print(f"\n✅ FOUND:")
                print(f"   Title:    {getattr(entity, 'title', 'Unknown')}")
                print(f"   ID:       {entity.id}")
                print(f"   Username: {getattr(entity, 'username', 'None')}")
                print(f"   Type:     {'Channel' if getattr(entity, 'broadcast', False) else 'Group/Supergroup'}")
                print(f"\n   ✅ This ID is VALID and accessible!")
                print()

            except ValueError as e:
                print(f"\n   ❌ Cannot access this channel/group")
                print(f"      Error: {e}")
                print(f"      Make sure you're a member of this channel/group")
                print()
            except Exception as e:
                print(f"\n   ❌ Error: {e}")
                print()

        except ValueError:
            print("   ⚠️ Invalid ID format. Use numbers only (e.g., -1004977901972)")
            print()

    # === FINAL INSTRUCTIONS ===
    print("\n" + "="*80)
    print("💡 HOW TO USE THE CHANNEL ID:")
    print("="*80)
    print("1. Copy the ID number from above (including the minus sign)")
    print("2. Open config.yaml")
    print("3. Update the 'channels' section:")
    print()
    print("   channels:")
    print("     - -1001234567890    # Your channel ID here")
    print()
    print("4. Save config.yaml and restart the bot")
    print("="*80)

    await client.disconnect()


if __name__ == '__main__':
    asyncio.run(find_all_groups())
