import discord
from discord import app_commands
from .base_tool import BaseTool
from datetime import datetime
import uuid


class PostManager(BaseTool):
    """Post Manager - Manages video posts with descriptions"""

    def __init__(self):
        super().__init__(
            tool_name="post",
            display_name="Confirmation-post",
            description="Gérer les posts",
            emoji="📢",
            json_file="tools/data/post_manager.json"
        )
        self.bot = None

    async def send_setup_embeds(self, bot, instance_id: str, setup_channel_id: int, admin_channel_id: int):
        """Send setup embeds to both channels"""
        self.bot = bot
        setup_channel = bot.get_channel(setup_channel_id)
        admin_channel = bot.get_channel(admin_channel_id)

        if not setup_channel or not admin_channel:
            return False

        # Setup channel - info message
        setup_embed = discord.Embed(
            title="📋 Reels — Validation",
            description=(
                "🎥 *Ce salon te permet de soumettre les Reels de la modèle avant publication.*\n\n"
                "**Voici comment faire :**\n"
                "- Publie le **Reel à valider** dans ce salon\n"
                "- Propose **3 textes** :\n"
                "  - 2 inspirés du Reel original\n"
                "  - 1 inventé par toi\n"
                "- L'équipe analysera ta proposition et validera le texte retenu\n\n"
                "✉️ *Tu recevras ensuite le texte final à publier au moment de la mise en ligne.*"
            ),
            color=discord.Color.from_rgb(255, 255, 255)
        )
        await setup_channel.send(embed=setup_embed)

        # Admin channel - info message
        admin_embed = discord.Embed(
            title="📢 Confirmation-post - Admin",
            description=(
                "📹 Ce salon sert à évaluer les vidéos proposées.\n\n"
                "Vous recevrez les vidéos avec leurs descriptions proposées.\n"
                "Sélectionnez la meilleure description et confirmez pour notifier l'utilisateur."
            ),
            color=discord.Color.from_rgb(255, 255, 255)
        )
        await admin_channel.send(embed=admin_embed)

        # Initialize instance data
        instance = self.get_instance(instance_id)
        if instance:
            if 'posts' not in instance:
                instance['posts'] = []
            for i, inst in enumerate(self.instances['instances']):
                if inst.get('instance_id') == instance_id:
                    self.instances['instances'][i] = instance
                    break
            self.save_instances()

        return True

    async def handle_video_message(self, message: discord.Message, instance_id: str):
        """Handle when a user posts a video in the setup channel"""
        # Check if message has video attachment
        video_attachment = None
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith('video/'):
                video_attachment = attachment
                break

        if not video_attachment:
            return

        # Create a new post entry
        post_id = str(uuid.uuid4())
        post_data = {
            'post_id': post_id,
            'user_id': message.author.id,
            'video_url': video_attachment.url,
            'video_message_id': message.id,
            'descriptions': [],
            'response_message_id': None,
            'admin_message_id': None,
            'status': 'draft',
            'created_at': datetime.now().isoformat()
        }

        # Send response embed
        embed = self.create_post_draft_embed(post_data, message.author)
        view = PostDraftView(self, instance_id, post_id)
        response_message = await message.reply(embed=embed, view=view)
        post_data['response_message_id'] = response_message.id

        # Save to instance
        instance = self.get_instance(instance_id)
        if instance:
            if 'posts' not in instance:
                instance['posts'] = []
            instance['posts'].append(post_data)
            for i, inst in enumerate(self.instances['instances']):
                if inst.get('instance_id') == instance_id:
                    self.instances['instances'][i] = instance
                    break
            self.save_instances()

    def create_post_draft_embed(self, post_data: dict, author: discord.User) -> discord.Embed:
        """Create the draft embed showing descriptions"""
        descriptions = post_data.get('descriptions', [])

        embed = discord.Embed(
            title="📹 Votre vidéo",
            description=f"Proposée par {author.mention}",
            color=discord.Color.from_rgb(255, 255, 255)
        )

        if descriptions:
            desc_text = ""
            for i, desc in enumerate(descriptions, 1):
                desc_text += f"**{i}.** {desc}\n"
            embed.add_field(
                name=f"📝 Descriptions ({len(descriptions)}/5)",
                value=desc_text,
                inline=False
            )
        else:
            embed.add_field(
                name="📝 Descriptions (0/5)",
                value="*Aucune description ajoutée*",
                inline=False
            )

        embed.set_footer(text="Ajoutez des descriptions puis envoyez pour évaluation")
        return embed

    async def add_description(self, bot, instance_id: str, post_id: str, description: str):
        """Add a description to a post"""
        instance = self.get_instance(instance_id)
        if not instance or 'posts' not in instance:
            return False

        post = next((p for p in instance['posts'] if p['post_id'] == post_id), None)
        if not post or len(post['descriptions']) >= 5:
            return False

        post['descriptions'].append(description)

        # Save
        for i, inst in enumerate(self.instances['instances']):
            if inst.get('instance_id') == instance_id:
                self.instances['instances'][i] = instance
                break
        self.save_instances()

        # Update the draft embed
        if post.get('response_message_id'):
            setup_channel = bot.get_channel(instance['setup_channel'])
            if setup_channel:
                try:
                    message = await setup_channel.fetch_message(post['response_message_id'])
                    # Get author
                    author = await bot.fetch_user(post['user_id'])
                    new_embed = self.create_post_draft_embed(post, author)
                    view = PostDraftView(self, instance_id, post_id)
                    await message.edit(embed=new_embed, view=view)
                except Exception as e:
                    print(f"Error updating post draft embed: {e}")

        return True

    async def remove_description(self, bot, instance_id: str, post_id: str, description_index: int):
        """Remove a description from a post"""
        instance = self.get_instance(instance_id)
        if not instance or 'posts' not in instance:
            return False

        post = next((p for p in instance['posts'] if p['post_id'] == post_id), None)
        if not post or description_index < 0 or description_index >= len(post['descriptions']):
            return False

        post['descriptions'].pop(description_index)

        # Save
        for i, inst in enumerate(self.instances['instances']):
            if inst.get('instance_id') == instance_id:
                self.instances['instances'][i] = instance
                break
        self.save_instances()

        # Update the draft embed
        if post.get('response_message_id'):
            setup_channel = bot.get_channel(instance['setup_channel'])
            if setup_channel:
                try:
                    message = await setup_channel.fetch_message(post['response_message_id'])
                    # Get author
                    author = await bot.fetch_user(post['user_id'])
                    new_embed = self.create_post_draft_embed(post, author)
                    view = PostDraftView(self, instance_id, post_id)
                    await message.edit(embed=new_embed, view=view)
                except Exception as e:
                    print(f"Error updating post draft embed: {e}")

        return True

    async def submit_for_review(self, bot, instance_id: str, post_id: str):
        """Submit post for admin review"""
        import aiohttp
        import io

        instance = self.get_instance(instance_id)
        if not instance or 'posts' not in instance:
            return False

        post = next((p for p in instance['posts'] if p['post_id'] == post_id), None)
        if not post or not post['descriptions']:
            return False

        post['status'] = 'pending'

        # Delete the draft message in setup channel
        if post.get('response_message_id'):
            setup_channel = bot.get_channel(instance['setup_channel'])
            if setup_channel:
                try:
                    message = await setup_channel.fetch_message(post['response_message_id'])
                    await message.delete()
                except:
                    pass

        # Send to admin channel
        admin_channel = bot.get_channel(instance['admin_channel'])
        if admin_channel:
            author = await bot.fetch_user(post['user_id'])

            embed = discord.Embed(
                title="📹 Nouvelle vidéo à évaluer",
                description=f"Proposée par {author.mention}",
                color=discord.Color.from_rgb(255, 255, 255)
            )

            desc_text = ""
            for i, desc in enumerate(post['descriptions'], 1):
                desc_text += f"**{i}.** {desc}\n"
            embed.add_field(
                name="📝 Descriptions proposées",
                value=desc_text,
                inline=False
            )

            view = AdminReviewView(self, instance_id, post_id, len(post['descriptions']))

            # Download video and send it with the embed
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(post['video_url']) as resp:
                        if resp.status == 200:
                            video_data = await resp.read()
                            video_file = discord.File(io.BytesIO(video_data), filename="video.mp4")
                            admin_message = await admin_channel.send(file=video_file, embed=embed, view=view)
                        else:
                            # Fallback to URL if download fails
                            embed.add_field(
                                name="🔗 Vidéo",
                                value=f"[Voir la vidéo]({post['video_url']})",
                                inline=False
                            )
                            admin_message = await admin_channel.send(embed=embed, view=view)
            except Exception as e:
                print(f"Error downloading video: {e}")
                # Fallback to URL
                embed.add_field(
                    name="🔗 Vidéo",
                    value=f"[Voir la vidéo]({post['video_url']})",
                    inline=False
                )
                admin_message = await admin_channel.send(embed=embed, view=view)

            post['admin_message_id'] = admin_message.id

        # Save
        for i, inst in enumerate(self.instances['instances']):
            if inst.get('instance_id') == instance_id:
                self.instances['instances'][i] = instance
                break
        self.save_instances()

        return True

    async def approve_post(self, bot, instance_id: str, post_id: str, selected_description: int):
        """Approve a post with selected description"""
        instance = self.get_instance(instance_id)
        if not instance or 'posts' not in instance:
            return False

        post = next((p for p in instance['posts'] if p['post_id'] == post_id), None)
        if not post:
            return False

        # Get the selected description
        if selected_description < 1 or selected_description > len(post['descriptions']):
            return False

        chosen_desc = post['descriptions'][selected_description - 1]

        # Send DM to user with video attached
        try:
            import aiohttp
            import io

            user = await bot.fetch_user(post['user_id'])

            # Build message link: https://discord.com/channels/{guild_id}/{channel_id}/{message_id}
            setup_channel = bot.get_channel(instance['setup_channel'])
            if setup_channel and setup_channel.guild:
                guild_id = setup_channel.guild.id
                channel_id = instance['setup_channel']
                message_id = post['video_message_id']
                video_message_link = f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"
            else:
                # Fallback to direct video URL if can't build message link
                video_message_link = post['video_url']

            dm_embed = discord.Embed(
                title="✅ Vidéo approuvée !",
                description="Votre vidéo a été validée par l'équipe.",
                color=discord.Color.from_rgb(255, 255, 255)
            )
            dm_embed.add_field(
                name="📝 Description à utiliser",
                value=f"**{chosen_desc}**",
                inline=False
            )
            dm_embed.add_field(
                name="🔗 Message original",
                value=f"[Voir le message]({video_message_link})",
                inline=False
            )

            # Download video and attach it to DM
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(post['video_url']) as resp:
                        if resp.status == 200:
                            video_data = await resp.read()
                            video_file = discord.File(io.BytesIO(video_data), filename="video.mp4")
                            await user.send(file=video_file, embed=dm_embed)
                        else:
                            # Fallback: send without video if download fails
                            await user.send(embed=dm_embed)
            except Exception as video_error:
                print(f"Error downloading video for DM: {video_error}")
                # Fallback: send without video
                await user.send(embed=dm_embed)

        except Exception as e:
            print(f"Error sending DM to user: {e}")

        # Delete admin message
        if post.get('admin_message_id'):
            admin_channel = bot.get_channel(instance['admin_channel'])
            if admin_channel:
                try:
                    message = await admin_channel.fetch_message(post['admin_message_id'])
                    await message.delete()
                except:
                    pass

        # Remove post from list
        instance['posts'].remove(post)

        # Save
        for i, inst in enumerate(self.instances['instances']):
            if inst.get('instance_id') == instance_id:
                self.instances['instances'][i] = instance
                break
        self.save_instances()

        return True

    async def setup_commands(self, bot):
        """Register PostManager-specific commands"""
        self.bot = bot


# Post Draft View (for setup channel)
class PostDraftView(discord.ui.View):
    def __init__(self, manager: PostManager, instance_id: str, post_id: str):
        super().__init__(timeout=None)
        self.manager = manager
        self.instance_id = instance_id
        self.post_id = post_id

        # Add Description button
        add_button = discord.ui.Button(
            label="Ajouter description",
            style=discord.ButtonStyle.primary,
            emoji="➕"
        )
        add_button.callback = self.add_description
        self.add_item(add_button)

        # Remove Description button
        remove_button = discord.ui.Button(
            label="Supprimer description",
            style=discord.ButtonStyle.danger,
            emoji="🗑️"
        )
        remove_button.callback = self.remove_description
        self.add_item(remove_button)

        # Submit button
        submit_button = discord.ui.Button(
            label="Faire évaluer",
            style=discord.ButtonStyle.green,
            emoji="📤"
        )
        submit_button.callback = self.submit_for_review
        self.add_item(submit_button)

    async def add_description(self, interaction: discord.Interaction):
        # Check if user is the author
        instance = self.manager.get_instance(self.instance_id)
        if not instance or 'posts' not in instance:
            await interaction.response.send_message(
                "❌ Erreur: Instance introuvable.",
                ephemeral=True,
                delete_after=60
            )
            return

        post = next((p for p in instance['posts'] if p['post_id'] == self.post_id), None)
        if not post:
            await interaction.response.send_message(
                "❌ Erreur: Post introuvable.",
                ephemeral=True,
                delete_after=60
            )
            return

        if post['user_id'] != interaction.user.id:
            await interaction.response.send_message(
                "❌ Seul l'auteur de la vidéo peut ajouter des descriptions.",
                ephemeral=True,
                delete_after=60
            )
            return

        if len(post['descriptions']) >= 5:
            await interaction.response.send_message(
                "❌ Vous avez atteint le maximum de 5 descriptions.",
                ephemeral=True,
                delete_after=60
            )
            return

        modal = AddDescriptionModal(self.manager, self.instance_id, self.post_id)
        await interaction.response.send_modal(modal)

    async def remove_description(self, interaction: discord.Interaction):
        # Check if user is the author
        instance = self.manager.get_instance(self.instance_id)
        if not instance or 'posts' not in instance:
            await interaction.response.send_message(
                "❌ Erreur: Instance introuvable.",
                ephemeral=True,
                delete_after=60
            )
            return

        post = next((p for p in instance['posts'] if p['post_id'] == self.post_id), None)
        if not post:
            await interaction.response.send_message(
                "❌ Erreur: Post introuvable.",
                ephemeral=True,
                delete_after=60
            )
            return

        if post['user_id'] != interaction.user.id:
            await interaction.response.send_message(
                "❌ Seul l'auteur de la vidéo peut supprimer des descriptions.",
                ephemeral=True,
                delete_after=60
            )
            return

        if not post['descriptions']:
            await interaction.response.send_message(
                "❌ Aucune description à supprimer.",
                ephemeral=True,
                delete_after=60
            )
            return

        # Create view with dropdown to select which description to remove
        view = RemoveDescriptionView(self.manager, self.instance_id, self.post_id, post['descriptions'])
        await interaction.response.send_message(
            "Sélectionnez la description à supprimer :",
            view=view,
            ephemeral=True,
            delete_after=60
        )

    async def submit_for_review(self, interaction: discord.Interaction):
        # Check if user is the author
        instance = self.manager.get_instance(self.instance_id)
        if not instance or 'posts' not in instance:
            await interaction.response.send_message(
                "❌ Erreur: Instance introuvable.",
                ephemeral=True,
                delete_after=60
            )
            return

        post = next((p for p in instance['posts'] if p['post_id'] == self.post_id), None)
        if not post:
            await interaction.response.send_message(
                "❌ Erreur: Post introuvable.",
                ephemeral=True,
                delete_after=60
            )
            return

        if post['user_id'] != interaction.user.id:
            await interaction.response.send_message(
                "❌ Seul l'auteur de la vidéo peut envoyer pour évaluation.",
                ephemeral=True,
                delete_after=60
            )
            return

        if not post['descriptions']:
            await interaction.response.send_message(
                "❌ Vous devez ajouter au moins une description.",
                ephemeral=True,
                delete_after=60
            )
            return

        # Defer response because video download takes time
        await interaction.response.defer(ephemeral=True)

        bot = interaction.client
        success = await self.manager.submit_for_review(bot, self.instance_id, self.post_id)

        if success:
            await interaction.followup.send(
                "✅ Votre vidéo a été envoyée pour évaluation !",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "❌ Erreur lors de l'envoi.",
                ephemeral=True
            )


# Remove Description View
class RemoveDescriptionView(discord.ui.View):
    def __init__(self, manager: PostManager, instance_id: str, post_id: str, descriptions: list):
        super().__init__(timeout=60)
        self.manager = manager
        self.instance_id = instance_id
        self.post_id = post_id

        # Create dropdown with all descriptions
        options = []
        for i, desc in enumerate(descriptions):
            preview = desc[:50]
            if len(desc) > 50:
                preview += "..."
            options.append(
                discord.SelectOption(
                    label=f"Description {i + 1}",
                    description=preview,
                    value=str(i),
                    emoji="📝"
                )
            )

        select = discord.ui.Select(
            placeholder="Choisissez la description à supprimer...",
            options=options
        )
        select.callback = self.on_select
        self.add_item(select)

    async def on_select(self, interaction: discord.Interaction):
        selected_index = int(self.children[0].values[0])

        bot = interaction.client
        success = await self.manager.remove_description(
            bot,
            self.instance_id,
            self.post_id,
            selected_index
        )

        if success:
            await interaction.response.send_message(
                "✅ Description supprimée !",
                ephemeral=True,
                delete_after=60
            )
        else:
            await interaction.response.send_message(
                "❌ Erreur lors de la suppression.",
                ephemeral=True,
                delete_after=60
            )


# Add Description Modal
class AddDescriptionModal(discord.ui.Modal):
    def __init__(self, manager: PostManager, instance_id: str, post_id: str):
        super().__init__(title="Ajouter une description")
        self.manager = manager
        self.instance_id = instance_id
        self.post_id = post_id

        self.description = discord.ui.TextInput(
            label="Description",
            placeholder="Entrez une description pour votre vidéo",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=200
        )
        self.add_item(self.description)

    async def on_submit(self, interaction: discord.Interaction):
        bot = interaction.client
        success = await self.manager.add_description(
            bot,
            self.instance_id,
            self.post_id,
            self.description.value
        )

        if success:
            await interaction.response.send_message(
                "✅ Description ajoutée !",
                ephemeral=True,
                delete_after=60
            )
        else:
            await interaction.response.send_message(
                "❌ Erreur lors de l'ajout de la description.",
                ephemeral=True,
                delete_after=60
            )


# Admin Review View
class AdminReviewView(discord.ui.View):
    def __init__(self, manager: PostManager, instance_id: str, post_id: str, num_descriptions: int):
        super().__init__(timeout=None)
        self.manager = manager
        self.instance_id = instance_id
        self.post_id = post_id

        # Add dropdown for selecting description
        options = [
            discord.SelectOption(
                label=f"Description {i}",
                value=str(i),
                emoji="📝"
            )
            for i in range(1, num_descriptions + 1)
        ]

        select = discord.ui.Select(
            placeholder="Choisissez la description...",
            options=options
        )
        select.callback = self.on_select
        self.add_item(select)

        # Add confirm button
        confirm_button = discord.ui.Button(
            label="Confirmer",
            style=discord.ButtonStyle.green,
            emoji="✅"
        )
        confirm_button.callback = self.confirm_selection
        self.add_item(confirm_button)

        self.selected_description = None

    async def on_select(self, interaction: discord.Interaction):
        self.selected_description = int(self.children[0].values[0])
        await interaction.response.send_message(
            f"✅ Description {self.selected_description} sélectionnée. Cliquez sur Confirmer pour valider.",
            ephemeral=True,
            delete_after=60
        )

    async def confirm_selection(self, interaction: discord.Interaction):
        if not self.manager.is_user_allowed(interaction.user.id):
            await interaction.response.send_message(
                "❌ Vous n'avez pas la permission de valider des posts.",
                ephemeral=True,
                delete_after=60
            )
            return

        if self.selected_description is None:
            await interaction.response.send_message(
                "❌ Veuillez d'abord sélectionner une description.",
                ephemeral=True,
                delete_after=60
            )
            return

        # Defer response because video download takes time
        await interaction.response.defer(ephemeral=True)

        bot = interaction.client
        success = await self.manager.approve_post(
            bot,
            self.instance_id,
            self.post_id,
            self.selected_description
        )

        if success:
            await interaction.followup.send(
                "✅ Vidéo approuvée ! L'utilisateur a été notifié par DM.",
                ephemeral=True
            )
        else:
            await interaction.followup.send(
                "❌ Erreur lors de l'approbation.",
                ephemeral=True
            )
