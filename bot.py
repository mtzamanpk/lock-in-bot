import discord
from discord import app_commands
from discord.ext import commands
import os  # Import os to access environment variables
import asyncio  # Import asyncio for async operations
import psycopg2  # Import PostgreSQL driver
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

# Database connection function
def get_db_connection():
    try:
        print(f"Attempting to connect to database with URL: {os.getenv('DATABASE_URL')[:20]}...")
        conn = psycopg2.connect(os.getenv('DATABASE_URL'))
        print("Database connection successful")
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

# Load user data from database
def load_user_data():
    print("Loading user data from database...")
    conn = get_db_connection()
    if not conn:
        print("No database connection, returning empty data")
        return {}
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get all checkins grouped by user, date, and category
            cur.execute("""
                SELECT user_id, checkin_date, category, activity
                FROM checkins
                ORDER BY checkin_date DESC, created_at ASC
            """)
            
            rows = cur.fetchall()
            print(f"Found {len(rows)} check-in records in database")
            
            # Organize data by user and date
            user_data = {}
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
            
            print(f"Organized data for {len(user_data)} users")
            return user_data
            
    except Exception as e:
        print(f"Error loading user data: {e}")
        return {}
    finally:
        conn.close()

# Save user data to database
def save_user_data(user_data):
    print("Saving user data to database...")
    conn = get_db_connection()
    if not conn:
        print("No database connection, cannot save data")
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
                            # Insert checkin (will skip duplicates due to UNIQUE constraint)
                            cur.execute("""
                                INSERT INTO checkins (user_id, checkin_date, category, activity)
                                VALUES (%s, %s, %s, %s)
                                ON CONFLICT (user_id, checkin_date, category, activity) DO NOTHING
                            """, (int(user_id), date, category, activity))
            
            conn.commit()
            print("Data saved successfully to database")
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
        print(f"Synced {len(synced)} command(s)")
        print("Synced commands:")
        for cmd in synced:
            print(f"  - /{cmd.name}: {cmd.description}")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    
    # Also print all registered commands
    print("\nAll registered commands:")
    for cmd in bot.tree.get_commands():
        print(f"  - /{cmd.name}: {cmd.description}")

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
        
        all_activities = []
        activity_mapping = {}  # Maps display number to (category, activity)
        display_number = 1
        
        for category_key in selected_categories:
            category = checklist_categories[category_key]
            activities_embed.add_field(name=f"**{category['name']}**", value="", inline=False)
            
            for activity in category['activities']:
                activities_embed.add_field(name=f"{display_number}. {activity}", value=f"({category['name']})", inline=True)
                activity_mapping[display_number] = (category_key, activity)
                all_activities.append(activity)
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
        
        # Get the current date
        from datetime import datetime
        current_date = datetime.now().strftime("%Y-%m-%d")

        # Load current user data from database
        current_user_data = load_user_data()
        
        # Store the activities with the date - consolidate by date
        if interaction.user.id not in current_user_data:
            current_user_data[interaction.user.id] = {}
        
        if current_date not in current_user_data[interaction.user.id]:
            current_user_data[interaction.user.id][current_date] = {
                'mental': [],
                'physical': [],
                'professional': []
            }
        
        # Add activities to their respective categories for the current date
        for item in selected_activities:
            category_key = item['category']
            if category_key in current_user_data[interaction.user.id][current_date]:
                # Check if activity already exists to avoid duplicates
                if item['activity'] not in current_user_data[interaction.user.id][current_date][category_key]:
                    current_user_data[interaction.user.id][current_date][category_key].append(item['activity'])
        
        # Save updated data to database
        save_user_data(current_user_data)
        
        # Create summary message
        summary = []
        for item in selected_activities:
            summary.append(f"{item['activity']} ({checklist_categories[item['category']]['name']})")
        
        await interaction.followup.send(f"✅ **Check-in recorded for {current_date}:**\n" + "\n".join([f"• {item}" for item in summary]))
        
    except asyncio.TimeoutError:
        await interaction.followup.send("⏰ You took too long to respond! Check-in cancelled.")

@bot.tree.command(name="mycheckins", description="View your previous check-ins")
async def mycheckins(interaction: discord.Interaction):
    print(f"User {interaction.user.id} ({interaction.user.name}) requested check-ins")
    
    # Always load fresh data from database
    current_user_data = load_user_data()
    print(f"Loaded data for {len(current_user_data)} users")
    
    # Display the user's previous check-ins with dates
    if interaction.user.id in current_user_data:
        checkins = current_user_data[interaction.user.id]
        print(f"Found {len(checkins)} dates for user {interaction.user.id}")
        
        if checkins:
            checkin_str = ""
            # Sort dates in reverse order (most recent first)
            sorted_dates = sorted(checkins.keys(), reverse=True)
            print(f"Sorted dates: {sorted_dates[:5]}...")  # Show first 5 dates
            
            for date in sorted_dates[:10]:  # Show last 10 dates
                checkin_str += f"📅 **{date}:**\n"
                
                # Check each category and display activities if they exist
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
        else:
            print("User has no check-ins")
            await interaction.response.send_message("You haven't checked in yet!")
    else:
        print(f"User {interaction.user.id} not found in data")
        await interaction.response.send_message("You haven't checked in yet!")

@bot.tree.command(name="help", description="Show available commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="Lock-in Bot Commands", description="Available commands:", color=discord.Color.blue())
    embed.add_field(name="/checkin", value="Start your daily check-in process with categories and activities", inline=False)
    embed.add_field(name="/mycheckins", value="View your previous check-ins", inline=False)
    embed.add_field(name="/help", value="Show this help message", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="debug", description="Debug database contents (admin only)")
async def debug_command(interaction: discord.Interaction):
    # Only allow the bot owner to use this command
    if interaction.user.id != 219995929254690816:  # Your user ID
        await interaction.response.send_message("❌ This command is for debugging only.")
        return
    
    print("Debug command executed")
    conn = get_db_connection()
    if not conn:
        await interaction.response.send_message("❌ Database connection failed")
        return
    
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Check users table
            cur.execute("SELECT * FROM users ORDER BY created_at DESC")
            users = cur.fetchall()
            
            # Check checkins table
            cur.execute("SELECT * FROM checkins ORDER BY created_at DESC LIMIT 10")
            checkins = cur.fetchall()
            
            debug_info = f"**Database Debug Info:**\n\n"
            debug_info += f"**Users ({len(users)}):**\n"
            for user in users:
                debug_info += f"• User ID: `{user['user_id']}` (Created: {user['created_at']})\n"
            
            debug_info += f"\n**Recent Check-ins ({len(checkins)}):**\n"
            for checkin in checkins:
                debug_info += f"• User: `{checkin['user_id']}` | Date: {checkin['checkin_date']} | Category: {checkin['category']} | Activity: {checkin['activity']}\n"
            
            await interaction.response.send_message(debug_info)
            
    except Exception as e:
        await interaction.response.send_message(f"❌ Error: {e}")
    finally:
        conn.close()

# Use environment variable for the bot token
bot.run(os.getenv('DISCORD_TOKEN'))
