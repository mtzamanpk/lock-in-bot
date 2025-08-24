import discord
from discord import app_commands
from discord.ext import commands
import os  # Import os to access environment variables
import json  # Import json for data handling
import asyncio  # Import asyncio for async operations

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

# Load user data from a JSON file
def load_user_data():
    try:
        with open('user_data.json', 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return {}

# Save user data to a JSON file
def save_user_data(data):
    with open('user_data.json', 'w') as file:
        json.dump(data, file)

user_data = load_user_data()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
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

        # Store the activities with the date - consolidate by date
        if interaction.user.id not in user_data:
            user_data[interaction.user.id] = {}
        
        if current_date not in user_data[interaction.user.id]:
            user_data[interaction.user.id][current_date] = {
                'mental': [],
                'physical': [],
                'professional': []
            }
        
        # Add activities to their respective categories for the current date
        for item in selected_activities:
            category_key = item['category']
            if category_key in user_data[interaction.user.id][current_date]:
                # Check if activity already exists to avoid duplicates
                if item['activity'] not in user_data[interaction.user.id][current_date][category_key]:
                    user_data[interaction.user.id][current_date][category_key].append(item['activity'])
        
        # Save updated data to the file
        save_user_data(user_data)
        
        # Create summary message
        summary = []
        for item in selected_activities:
            summary.append(f"{item['activity']} ({checklist_categories[item['category']]['name']})")
        
        await interaction.followup.send(f"✅ **Check-in recorded for {current_date}:**\n" + "\n".join([f"• {item}" for item in summary]))
        
    except asyncio.TimeoutError:
        await interaction.followup.send("⏰ You took too long to respond! Check-in cancelled.")

@bot.tree.command(name="mycheckins", description="View your previous check-ins")
async def mycheckins(interaction: discord.Interaction):
    # Display the user's previous check-ins with dates
    if interaction.user.id in user_data:
        checkins = user_data[interaction.user.id]
        if checkins:
            checkin_str = ""
            # Sort dates in reverse order (most recent first)
            sorted_dates = sorted(checkins.keys(), reverse=True)
            
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
            await interaction.response.send_message("You haven't checked in yet!")
    else:
        await interaction.response.send_message("You haven't checked in yet!")

@bot.tree.command(name="help", description="Show available commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="Lock-in Bot Commands", description="Available commands:", color=discord.Color.blue())
    embed.add_field(name="/checkin", value="Start your daily check-in process with categories and activities", inline=False)
    embed.add_field(name="/mycheckins", value="View your previous check-ins", inline=False)
    embed.add_field(name="/help", value="Show this help message", inline=False)
    await interaction.response.send_message(embed=embed)

# Use environment variable for the bot token
bot.run(os.getenv('DISCORD_TOKEN'))  # Replace with your bot's token
