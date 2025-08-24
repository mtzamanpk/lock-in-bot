import discord
from discord.ext import commands
import os  # Import os to access environment variables

# Create bot instance
bot = commands.Bot(command_prefix="!")

# A simple checklist (you can expand this)
checklist = ["Work", "Exercise", "Read", "Cook", "Learn something new"]

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

@bot.command()
async def checkin(ctx):
    # Ask the user what they did today from a checklist
    embed = discord.Embed(title="What did you do today?")
    embed.description = "\n".join([f"{index + 1}. {item}" for index, item in enumerate(checklist)])
    await ctx.send(embed=embed)
    
    # Create a response listener
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel
    
    try:
        msg = await bot.wait_for('message', check=check, timeout=30.0)
        activities = [checklist[int(x)-1] for x in msg.content.split() if x.isdigit()]
        
        # Get the current date
        from datetime import datetime
        current_date = datetime.now().strftime("%Y-%m-%d")

        # Store the activities with the date
        if ctx.author.id not in user_data:
            user_data[ctx.author.id] = []
        
        user_data[ctx.author.id].append({'date': current_date, 'activities': activities})
        
        # Save updated data to the file
        save_user_data(user_data)
        
        await ctx.send(f"Your check-in for {current_date} was recorded: {', '.join(activities)}")
    except asyncio.TimeoutError:
        await ctx.send("You took too long to respond!")

@bot.command()
async def mycheckins(ctx):
    # Display the user's previous check-ins with dates
    if ctx.author.id in user_data:
        checkins = user_data[ctx.author.id]
        checkin_str = "\n".join([f"{checkin['date']}: {', '.join(checkin['activities'])}" for checkin in checkins])
        await ctx.send(f"Your previous check-ins:\n{checkin_str}")
    else:
        await ctx.send("You haven't checked in yet!")

# Use environment variable for the bot token
bot.run(os.getenv('DISCORD_TOKEN'))  # Replace with your bot's token
