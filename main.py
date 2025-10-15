import discord
from discord import app_commands
from discord.ext import commands
import json

# Import tool classes
from tools.core import ActivityManager, TaskManager, ReviewManager, PostManager

# Load configuration
def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

config = load_config()

# Bot setup with intents
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents
        )

    async def setup_hook(self):
        # Register all tool-specific commands
        for tool in TOOLS:
            await tool.setup_commands(self)

        # Sync commands globally
        await self.tree.sync()
        print("Synced commands globally")

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')
        print('------')

        # Clear all instances from JSON files on bot start
        for tool in TOOLS:
            tool.instances['instances'] = []
            tool.save_instances()
            print(f"Cleared instances for {tool.display_name}")

        # Set bot status
        activity = discord.Game(name=config['bot_settings']['activity'])
        await self.change_presence(
            status=discord.Status[config['bot_settings']['status']],
            activity=activity
        )

        print("Bot is ready and all instances are cleared!")

    async def on_message(self, message: discord.Message):
        # Ignore bot messages
        if message.author.bot:
            return

        # Check if message has video attachments
        has_video = any(
            attachment.content_type and attachment.content_type.startswith('video/')
            for attachment in message.attachments
        )

        if not has_video:
            return

        # Check if message is in a PostManager setup channel
        for tool in TOOLS:
            if tool.tool_name == 'post':
                for instance in tool.instances.get('instances', []):
                    if instance.get('setup_channel') == message.channel.id:
                        await tool.handle_video_message(message, instance['instance_id'])
                        break

bot = MyBot()

# Initialize all tools
TOOLS = [
    ActivityManager(),
    TaskManager(),
    ReviewManager(),
    PostManager()
]

# Tool Select Dropdown
class ToolSelect(discord.ui.Select):
    def __init__(self, tools):
        self.tools_dict = {tool.tool_name: tool for tool in tools}

        options = [
            discord.SelectOption(
                label=tool.display_name,
                description=tool.description,
                value=tool.tool_name,
                emoji=tool.emoji
            )
            for tool in tools
        ]

        super().__init__(
            placeholder="Sélectionnez un outil à configurer...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_tool = self.tools_dict[self.values[0]]
        await interaction.response.send_modal(SetupModal(selected_tool))

# Tool Select View
class ToolSelectView(discord.ui.View):
    def __init__(self, tools):
        super().__init__(timeout=60)
        self.add_item(ToolSelect(tools))

# Setup Modal
class SetupModal(discord.ui.Modal):
    def __init__(self, tool_manager):
        super().__init__(title=f"Configuration {tool_manager.display_name}")
        self.tool_manager = tool_manager

        self.admin_channel_id = discord.ui.TextInput(
            label="ID du salon admin",
            placeholder="Entrez l'ID du salon admin",
            required=True,
            max_length=20
        )
        self.add_item(self.admin_channel_id)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            admin_channel_id = int(self.admin_channel_id.value)
            admin_channel = bot.get_channel(admin_channel_id)

            if admin_channel is None:
                await interaction.response.send_message(
                    f"❌ Salon avec l'ID {admin_channel_id} introuvable ou le bot n'y a pas accès !",
                    ephemeral=True,
                    delete_after=60
                )
                return

            # The channel where the setup command was executed
            setup_channel_id = interaction.channel_id

            instance_id, error = self.tool_manager.add_instance(
                interaction.guild.id,
                setup_channel_id,
                admin_channel_id
            )

            # Check if instance creation failed
            if instance_id is None:
                if error == "setup_channel":
                    await interaction.response.send_message(
                        f"❌ Une instance de {self.tool_manager.display_name} existe déjà avec ce salon de configuration !\n"
                        f"Utilisez un salon différent ou supprimez l'instance existante.",
                        ephemeral=True,
                        delete_after=60
                    )
                elif error == "admin_channel":
                    await interaction.response.send_message(
                        f"❌ Une instance de {self.tool_manager.display_name} existe déjà avec ce salon admin !\n"
                        f"Utilisez un salon différent ou supprimez l'instance existante.",
                        ephemeral=True,
                        delete_after=60
                    )
                return

            # Send setup embeds if tool supports it
            if hasattr(self.tool_manager, 'send_setup_embeds'):
                success = await self.tool_manager.send_setup_embeds(
                    bot,
                    instance_id,
                    setup_channel_id,
                    admin_channel_id
                )
                if not success:
                    await interaction.response.send_message(
                        f"⚠️ Configuration sauvegardée mais impossible d'envoyer les embeds.",
                        ephemeral=True,
                        delete_after=60
                    )
                    return

            await interaction.response.send_message(
                f"✅ {self.tool_manager.display_name} a été configuré !\n"
                f"Salon de configuration : <#{setup_channel_id}>\n"
                f"Salon admin : {admin_channel.mention}",
                ephemeral=True,
                delete_after=60
            )
        except ValueError:
            await interaction.response.send_message(
                "❌ ID de salon invalide ! Veuillez entrer un nombre valide.",
                ephemeral=True,
                delete_after=60
            )

# Setup Command
@bot.tree.command(name="setup", description="Configurer un outil pour ce serveur")
async def setup(interaction: discord.Interaction):
    # Check if user is allowed to setup tools
    allowed_ids = config.get('allowed_user_ids', [])
    if allowed_ids and interaction.user.id not in allowed_ids:
        await interaction.response.send_message(
            "❌ Vous n'avez pas la permission d'utiliser cette commande.",
            ephemeral=True,
            delete_after=60
        )
        return

    view = ToolSelectView(TOOLS)
    await interaction.response.send_message(
        "Sélectionnez un outil à configurer :",
        view=view,
        ephemeral=True,
        delete_after=60
    )

# Traditional command for syncing
@bot.command()
async def sync(ctx):
    """Manually sync slash commands (owner only)"""
    if ctx.author.id == ctx.guild.owner_id:
        await bot.tree.sync()
        await ctx.send("Commandes synchronisées globalement !")
    else:
        await ctx.send("Vous n'avez pas la permission d'utiliser cette commande.")

# Run the bot
if __name__ == "__main__":
    bot.run(config['token'])
