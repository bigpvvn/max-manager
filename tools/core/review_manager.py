import discord
from discord import app_commands
from .base_tool import BaseTool
from datetime import datetime


class ReviewManager(BaseTool):
    """Review Manager - Manages feedback forwarding"""

    def __init__(self):
        super().__init__(
            tool_name="review",
            display_name="Feedback",
            description="Gérer les retours",
            emoji="📝",
            json_file="tools/data/review_manager.json"
        )
        self.bot = None

    async def send_setup_embeds(self, bot, instance_id: str, setup_channel_id: int, admin_channel_id: int):
        """Send setup embeds to both channels"""
        self.bot = bot
        setup_channel = bot.get_channel(setup_channel_id)
        admin_channel = bot.get_channel(admin_channel_id)

        if not setup_channel or not admin_channel:
            return False

        # Setup channel - info embed
        setup_embed = discord.Embed(
            title="📝 Feedback",
            description=(
                "Ce salon centralise les **retours** et **échanges importants** de l'équipe. 📢\n"
                "Vous y trouverez des **suggestions**, **avis** ou **commentaires** concernant différents aspects du travail.\n\n"
                "*Consultez-le régulièrement pour rester à jour et continuer à progresser !*"
            ),
            color=discord.Color.from_rgb(255, 255, 255)
        )
        await setup_channel.send(embed=setup_embed)

        # Admin channel - control panel
        admin_embed = discord.Embed(
            title="📝 Feedback",
            description="Panneau de contrôle pour envoyer des feedbacks aux utilisateurs.",
            color=discord.Color.from_rgb(255, 255, 255),
            timestamp=datetime.now()
        )
        admin_embed.add_field(
            name="💡 Comment ça marche ?",
            value=(
                "Cliquez sur le bouton **➕ Envoyer un feedback** ci-dessous pour envoyer un message.\n\n"
                "Le feedback sera immédiatement envoyé dans le salon de configuration."
            ),
            inline=False
        )

        view = AdminFeedbackView(self, instance_id)
        await admin_channel.send(embed=admin_embed, view=view)

        return True

    async def send_feedback_to_setup(self, instance_id: str, content: str, author_name: str):
        """Send feedback message to setup channel"""
        if not self.bot:
            return False

        instance = self.get_instance(instance_id)
        if not instance:
            return False

        setup_channel = self.bot.get_channel(instance['setup_channel'])
        if not setup_channel:
            return False

        # Create feedback embed
        feedback_embed = discord.Embed(
            title="📝 Nouveau Feedback",
            description=content,
            color=discord.Color.from_rgb(255, 255, 255),
            timestamp=datetime.now()
        )
        feedback_embed.set_footer(text=f"Par {author_name}")
        feedback_embed.set_image(url="attachment://feedback.png")

        # Send with image attachment
        try:
            file = discord.File("img/feedback.png", filename="feedback.png")
            await setup_channel.send(file=file, embed=feedback_embed)
        except FileNotFoundError:
            # Fallback: send without image if file not found
            print("Warning: img/feedback.png not found, sending feedback without image")
            await setup_channel.send(embed=feedback_embed)
        except Exception as e:
            print(f"Error sending feedback with image: {e}")
            return False

        return True


    async def setup_commands(self, bot):
        """Register ReviewManager-specific commands"""
        self.bot = bot


# Admin Feedback View
class AdminFeedbackView(discord.ui.View):
    def __init__(self, manager: ReviewManager, instance_id: str):
        super().__init__(timeout=None)
        self.manager = manager
        self.instance_id = instance_id

    @discord.ui.button(label="Envoyer un feedback", style=discord.ButtonStyle.primary, emoji="➕")
    async def send_feedback(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Check permission
        if not self.manager.is_user_allowed(interaction.user.id):
            await interaction.response.send_message(
                "❌ Vous n'avez pas la permission d'envoyer des feedbacks.",
                ephemeral=True,
                delete_after=60
            )
            return

        modal = SendFeedbackModal(self.manager, self.instance_id)
        await interaction.response.send_modal(modal)


# Send Feedback Modal
class SendFeedbackModal(discord.ui.Modal):
    def __init__(self, manager: ReviewManager, instance_id: str):
        super().__init__(title="Envoyer un feedback")
        self.manager = manager
        self.instance_id = instance_id

        self.content = discord.ui.TextInput(
            label="Contenu du feedback",
            placeholder="Écrivez votre message ici...",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=2000
        )
        self.add_item(self.content)

    async def on_submit(self, interaction: discord.Interaction):
        success = await self.manager.send_feedback_to_setup(
            self.instance_id,
            self.content.value,
            interaction.user.name
        )

        if success:
            await interaction.response.send_message(
                "✅ Feedback envoyé avec succès !",
                ephemeral=True,
                delete_after=60
            )
        else:
            await interaction.response.send_message(
                "❌ Erreur lors de l'envoi du feedback.",
                ephemeral=True,
                delete_after=60
            )
