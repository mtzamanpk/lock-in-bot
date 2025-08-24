import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
import psycopg2
from psycopg2.extras import RealDictCursor

# Create bot instance with intents (need message_content to read user responses)
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# A hierarchical checklist system
checklist_categories = {
    "mental": {
        "name": "Mental & Spiritual",
        "activities": ["Prayed Fajr", "Prayed Dhur", "Prayed Asr", "Prayed Maghrib", "Prayed Isha", "Read Quran"]
    },
    "physical": {
        "name": "Physical & Health",
        "activities": ["Went on a walk", "Gym workout", "Other form of workout", "Slept 8 hours"]
    },
    "professional": {
        "name": "Professional & Learning",
        "activities": ["LeetCode", "Side project", "Resume work", "YouTube learning", "Read a book"]
    }
}

def get_db_connection() -> Optional[psycopg2.extensions.connection]:
    """Establish database connection."""
    try:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            print("DATABASE_URL environment variable not set")
            return None

        conn = psycopg2.connect(database_url)
        return conn
    except Exception as e:
        print(f"Database connection failed: {e}")
        return None

# Initialize database tables
def init_database():
    print("Initializing database...")
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                # Create users table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create checkins table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS checkins (
                        id SERIAL PRIMARY KEY,
                        user_id BIGINT REFERENCES users(user_id),
                        checkin_date DATE NOT NULL,
                        category VARCHAR(20) NOT NULL,
                        activity VARCHAR(100) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(user_id, checkin_date, category, activity)
                    )
                """)
                
                conn.commit()
                print("Database initialized successfully")
        except Exception as e:
            print(f"Database initialization failed: {e}")
        finally:
            conn.close()
    else:
        print("Failed to initialize database - no connection")

def load_user_data() -> Dict[str, Dict[str, Dict[str, List[str]]]]:
    """Load all user check-in data from database.

    Returns:
        Dictionary structure: {user_id: {date: {category: [activities]}}}
    """
    conn = get_db_connection()
    if not conn:
        return {}

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT user_id, checkin_date, category, activity
                FROM checkins
                ORDER BY checkin_date DESC, created_at ASC
            """)

            rows = cur.fetchall()
            user_data: Dict[str, Dict[str, Dict[str, List[str]]]] = {}

            for row in rows:
                user_id = str(row['user_id'])
                date = row['checkin_date'].strftime('%Y-%m-%d')
                category = row['category']
                activity = row['activity']

                if user_id not in user_data:
                    user_data[user_id] = {}

                if date not in user_data[user_id]:
                    user_data[user_id][date] = {
                        'mental': [],
                        'physical': [],
                        'professional': []
                    }

                if activity not in user_data[user_id][date][category]:
                    user_data[user_id][date][category].append(activity)

            return user_data

    except Exception as e:
        print(f"Error loading user data: {e}")
        return {}
    finally:
        conn.close()

def save_user_data(user_data: Dict[str, Dict[str, Dict[str, List[str]]]]) -> bool:
    """Save user check-in data to database.

    Args:
        user_data: Dictionary structure {user_id: {date: {category: [activities]}}}

    Returns:
        True if successful, False otherwise
    """
    conn = get_db_connection()
    if not conn:
        return False

    try:
        with conn.cursor() as cur:
            for user_id, dates in user_data.items():
                # Ensure user exists
                cur.execute("""
                    INSERT INTO users (user_id)
                    VALUES (%s)
                    ON CONFLICT (user_id) DO NOTHING
                """, (int(user_id),))

                for date, categories in dates.items():
                    for category, activities in categories.items():
                        for activity in activities:
                            cur.execute("""
                                INSERT INTO checkins (user_id, checkin_date, category, activity)
                                VALUES (%s, %s, %s, %s)
                                ON CONFLICT (user_id, checkin_date, category, activity) DO NOTHING
                            """, (int(user_id), date, category, activity))

            conn.commit()
            return True

    except Exception as e:
        print(f"Error saving user data: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

# Initialize database on startup
init_database()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Successfully synced {len(synced)} commands")
        for cmd in synced:
            print(f"  - /{cmd.name}: {cmd.description}")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

@bot.tree.command(name="checkin", description="Check in with your daily activities")
async def checkin(interaction: discord.Interaction):
    # First, show the main categories
    embed = discord.Embed(title="🏆 Daily Check-in - Choose Categories", description="Select the main categories you want to check in for:", color=discord.Color.blue())
    
    for i, (key, category) in enumerate(checklist_categories.items(), 1):
        embed.add_field(name=f"{i}. {category['name']}", value=f"({len(category['activities'])} activities)", inline=False)
    
    embed.set_footer(text="Reply with the numbers of categories you want to check in for (e.g., 1 2)")
    
    await interaction.response.send_message(embed=embed)
    
    # Wait for category selection
    def check_category(m):
        return m.author == interaction.user and m.channel == interaction.channel
    
    try:
        category_msg = await bot.wait_for('message', check=check_category, timeout=60.0)
        
        # Parse category selection
        try:
            category_numbers = [int(x) for x in category_msg.content.split() if x.isdigit()]
            selected_categories = []
            
            for num in category_numbers:
                if 1 <= num <= len(checklist_categories):
                    category_key = list(checklist_categories.keys())[num-1]
                    selected_categories.append(category_key)
                else:
                    await interaction.followup.send(f"Category number {num} is out of range. Please use numbers 1-{len(checklist_categories)}.")
                    return
            
            if not selected_categories:
                await interaction.followup.send("No valid categories selected.")
                return
                
        except (ValueError, IndexError) as e:
            await interaction.followup.send(f"Invalid input. Please use numbers 1-{len(checklist_categories)}.")
            return
        
        # Now show activities for selected categories
        activities_embed = discord.Embed(title="📋 Select Activities", description="Choose the activities you completed:", color=discord.Color.green())
        
        activity_mapping = {}  # Maps display number to (category, activity)
        display_number = 1

        for category_key in selected_categories:
            category = checklist_categories[category_key]
            activities_embed.add_field(name=f"**{category['name']}**", value="", inline=False)

            for activity in category['activities']:
                activities_embed.add_field(name=f"{display_number}. {activity}", value=f"({category['name']})", inline=True)
                activity_mapping[display_number] = (category_key, activity)
                display_number += 1
        
        activities_embed.set_footer(text=f"Reply with the numbers of activities you completed (e.g., 1 3 5)")
        
        await interaction.followup.send(embed=activities_embed)
        
        # Wait for activity selection
        def check_activities(m):
            return m.author == interaction.user and m.channel == interaction.channel
        
        activity_msg = await bot.wait_for('message', check=check_activities, timeout=60.0)
        
        # Parse activity selection
        try:
            activity_numbers = [int(x) for x in activity_msg.content.split() if x.isdigit()]
            selected_activities = []
            
            for num in activity_numbers:
                if num in activity_mapping:
                    category_key, activity = activity_mapping[num]
                    selected_activities.append({
                        'category': category_key,
                        'activity': activity
                    })
                else:
                    await interaction.followup.send(f"Activity number {num} is not valid. Please use numbers from the list above.")
                    return
            
            if not selected_activities:
                await interaction.followup.send("No valid activities selected.")
                return
                
        except (ValueError, IndexError) as e:
            await interaction.followup.send(f"Invalid input. Please use numbers from the activities list.")
            return
        
        # Get the current date and save check-ins
        current_date = datetime.now().strftime("%Y-%m-%d")
        current_user_data = load_user_data()

        # Initialize user data structure if needed
        user_id_str = str(interaction.user.id)
        if user_id_str not in current_user_data:
            current_user_data[user_id_str] = {}

        if current_date not in current_user_data[user_id_str]:
            current_user_data[user_id_str][current_date] = {
                'mental': [],
                'physical': [],
                'professional': []
            }

        # Add activities to their respective categories
        for item in selected_activities:
            category_key = item['category']
            activity = item['activity']
            if activity not in current_user_data[user_id_str][current_date][category_key]:
                current_user_data[user_id_str][current_date][category_key].append(activity)

        # Save to database and send confirmation
        save_user_data(current_user_data)

        summary = [f"{item['activity']} ({checklist_categories[item['category']]['name']})"
                  for item in selected_activities]

        await interaction.followup.send(f"✅ **Check-in recorded for {current_date}:**\n" +
                                       "\n".join([f"• {item}" for item in summary]))
        
    except asyncio.TimeoutError:
        await interaction.followup.send("⏰ You took too long to respond! Check-in cancelled.")


@bot.tree.command(name="mycheckins", description="View your own check-ins")
async def mycheckins(interaction: discord.Interaction):
    current_user_data = load_user_data()
    user_id_str = str(interaction.user.id)

    if user_id_str not in current_user_data or not current_user_data[user_id_str]:
        await interaction.response.send_message("You haven't checked in yet!")
        return

    checkins = current_user_data[user_id_str]
    sorted_dates = sorted(checkins.keys(), reverse=True)

    checkin_str = ""
    for date in sorted_dates[:10]:  # Show last 10 dates
        checkin_str += f"📅 **{date}:**\n"

        for category_key in ['mental', 'physical', 'professional']:
            if category_key in checkins[date] and checkins[date][category_key]:
                category_name = checklist_categories[category_key]['name']
                activities = checkins[date][category_key]
                checkin_str += f"  **{category_name}:**\n"
                for activity in activities:
                    checkin_str += f"    • {activity}\n"

        checkin_str += "\n"

    embed = discord.Embed(title="Your Previous Check-ins", description=checkin_str, color=discord.Color.green())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="deletecheckin", description="Delete check-ins for a specific date")
async def deletecheckin(interaction: discord.Interaction):
    current_user_data = load_user_data()
    user_id_str = str(interaction.user.id)

    if user_id_str not in current_user_data or not current_user_data[user_id_str]:
        await interaction.response.send_message("You have no check-ins to delete!")
        return

    user_dates = current_user_data[user_id_str]
    date_list = list(sorted(user_dates.keys(), reverse=True))

    # Create selection embed
    embed = discord.Embed(title="🗑️ Delete Check-ins",
                         description="Select which date's check-ins you want to delete:",
                         color=discord.Color.red())

    for i, date in enumerate(date_list, 1):
        activities_summary = []
        for category_key in ['mental', 'physical', 'professional']:
            if category_key in user_dates[date] and user_dates[date][category_key]:
                category_name = checklist_categories[category_key]['name']
                activities_summary.append(f"{category_name}: {len(user_dates[date][category_key])}")

        activities_str = ", ".join(activities_summary) if activities_summary else "No activities"
        embed.add_field(name=f"{i}. {date}", value=f"📝 {activities_str}", inline=False)

    embed.set_footer(text="Reply with the number of the date you want to delete, or 'cancel' to cancel")
    await interaction.response.send_message(embed=embed)

    def check_selection(m):
        return m.author == interaction.user and m.channel == interaction.channel

    try:
        selection_msg = await bot.wait_for('message', check=check_selection, timeout=60.0)
        selection = selection_msg.content.strip().lower()

        if selection == 'cancel':
            await interaction.followup.send("❌ Deletion cancelled.")
            return

        try:
            selection_num = int(selection)
            if 1 <= selection_num <= len(date_list):
                selected_date = date_list[selection_num - 1]

                # Delete from database
                conn = get_db_connection()
                if conn:
                    try:
                        with conn.cursor() as cur:
                            cur.execute("""
                                DELETE FROM checkins
                                WHERE user_id = %s AND checkin_date = %s
                            """, (interaction.user.id, selected_date))

                            deleted_count = cur.rowcount
                            conn.commit()

                        await interaction.followup.send(f"✅ Deleted {deleted_count} check-in(s) for {selected_date}")

                    except Exception as e:
                        print(f"Error deleting check-ins: {e}")
                        await interaction.followup.send("❌ Error deleting check-ins")
                    finally:
                        conn.close()
                else:
                    await interaction.followup.send("❌ Database connection failed")
            else:
                await interaction.followup.send(f"❌ Invalid selection. Please choose a number between 1 and {len(date_list)}.")

        except ValueError:
            await interaction.followup.send("❌ Please enter a valid number or 'cancel'.")

    except asyncio.TimeoutError:
        await interaction.followup.send("⏰ You took too long to respond! Deletion cancelled.")

# Use environment variable for the bot token
bot.run(os.getenv('DISCORD_TOKEN'))
