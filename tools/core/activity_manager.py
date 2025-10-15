import discord
from discord import app_commands
from .base_tool import BaseTool
from .pagination import PaginatedEmbed, PaginationView
import asyncio
from datetime import datetime, timedelta


class ActivityManager(BaseTool):
    """Activity Manager - Manages activity tracking"""

    def __init__(self):
        super().__init__(
            tool_name="activity",
            display_name="Pointeuse",
            description="Gérer le suivi d'activité",
            emoji="📊",
            json_file="tools/data/activity_manager.json"
        )
        self.pause_tasks = {}  # Store active pause timers: {(instance_id, user_id): task}
        self.refresh_tasks = {}  # Store auto-refresh tasks: {instance_id: task}
        self.bot = None  # Will be set in setup_commands

    async def send_setup_embeds(self, bot, instance_id: str, setup_channel_id: int, admin_channel_id: int):
        """Send setup embeds to both channels"""
        setup_channel = bot.get_channel(setup_channel_id)
        admin_channel = bot.get_channel(admin_channel_id)

        if not setup_channel or not admin_channel:
            return False

        # Setup channel embed with buttons
        setup_embed = discord.Embed(
            title="📊 Pointeuse",
            description=(
                "👉 Ce salon est **obligatoire** pour suivre ton activité.\n"
                "Utilise les **boutons ci-dessous** selon ta situation :\n\n"
                "- **Début de shift** → Démarre ton shift\n"
                "- **Pause** → Indique une pause (ex : 15 minutes)\n"
                "- **Fin de shift** → Termine ton shift\n\n"
                "📝 Pense à pointer ici **et sur Offmy** pour une organisation claire et efficace."
            ),
            color=discord.Color.from_rgb(255, 255, 255)
        )

        view = ActivityButtonsView(self, instance_id)
        await setup_channel.send(content="@everyone", embed=setup_embed, view=view)

        # Admin channel - send initial status embed with pagination
        admin_embed = self.create_status_embed(instance_id, page=0)
        admin_view = AdminPanelView(self, instance_id, page=0)
        admin_message = await admin_channel.send(embed=admin_embed, view=admin_view)

        # Store admin message ID for updates
        instance = self.get_instance(instance_id)
        if instance:
            instance['admin_message_id'] = admin_message.id
            instance['admin_page'] = 0  # Track current page
            for i, inst in enumerate(self.instances['instances']):
                if inst.get('instance_id') == instance_id:
                    self.instances['instances'][i] = instance
                    break
            self.save_instances()

        # Start auto-refresh task (cancel existing if any)
        if instance_id in self.refresh_tasks:
            self.refresh_tasks[instance_id].cancel()

        refresh_task = asyncio.create_task(self.auto_refresh_admin_panel(bot, instance_id, admin_channel_id))
        self.refresh_tasks[instance_id] = refresh_task

        return True

    def create_status_embed(self, instance_id: str, page: int = 0) -> discord.Embed:
        """Create the status embed for admin panel with pagination"""
        instance = self.get_instance(instance_id)
        users = instance.get('users', {}) if instance else {}

        # Convert to list for pagination
        users_list = list(users.items())

        status_emojis = {
            'active': '🟢',
            'pause': '🟡',
            'ended': '🔴'
        }

        def format_user(user_data):
            user_id, data = user_data
            status = data['status']
            emoji = status_emojis.get(status, '⚪')

            status_text = {
                'active': 'En shift',
                'pause': f"En pause ({data.get('pause_duration', '?')} min)",
                'ended': 'Shift terminé'
            }.get(status, 'Inconnu')

            last_action = data.get('last_action', 'Jamais')
            if last_action != 'Jamais':
                try:
                    dt = datetime.fromisoformat(last_action)
                    last_action = f"<t:{int(dt.timestamp())}:R>"
                except:
                    pass

            return f"{emoji} <@{user_id}>\n**Statut:** {status_text}\n**Dernière action:** {last_action}\n"

        # Créer l'embed paginé
        paginated = PaginatedEmbed(
            title="📊 Pointeuse",
            description="Statut en temps réel de tous les utilisateurs",
            color=discord.Color.from_rgb(255, 255, 255),
            footer_text="Mise à jour automatique toutes les 60s",
            items_per_page=5,
            max_chars_per_page=1900
        )

        paginated.add_section(
            name="",
            items=users_list,
            formatter=format_user,
            empty_message="Aucun utilisateur n'a commencé son shift.",
            inline=False
        )

        pages = paginated.generate_pages()

        # S'assurer que la page demandée existe
        page = max(0, min(page, len(pages) - 1))

        return pages[page]

    async def auto_refresh_admin_panel(self, bot, instance_id: str, admin_channel_id: int):
        """Auto-refresh admin panel every 60 seconds - one task per instance"""
        await bot.wait_until_ready()

        while not bot.is_closed():
            try:
                instance = self.get_instance(instance_id)
                if not instance or 'admin_message_id' not in instance:
                    if instance_id in self.refresh_tasks:
                        del self.refresh_tasks[instance_id]
                    break

                admin_channel = bot.get_channel(admin_channel_id)
                if not admin_channel:
                    if instance_id in self.refresh_tasks:
                        del self.refresh_tasks[instance_id]
                    break

                try:
                    admin_message = await admin_channel.fetch_message(instance['admin_message_id'])
                    current_page = instance.get('admin_page', 0)
                    new_embed = self.create_status_embed(instance_id, page=current_page)
                    admin_view = AdminPanelView(self, instance_id, page=current_page)
                    await admin_message.edit(embed=new_embed, view=admin_view)
                except discord.NotFound:
                    new_embed = self.create_status_embed(instance_id, page=0)
                    admin_view = AdminPanelView(self, instance_id, page=0)
                    admin_message = await admin_channel.send(embed=new_embed, view=admin_view)
                    instance['admin_message_id'] = admin_message.id
                    instance['admin_page'] = 0
                    for i, inst in enumerate(self.instances['instances']):
                        if inst.get('instance_id') == instance_id:
                            self.instances['instances'][i] = instance
                            break
                    self.save_instances()

            except Exception as e:
                print(f"Error refreshing admin panel for instance {instance_id}: {e}")

            await asyncio.sleep(60)

        if instance_id in self.refresh_tasks:
            del self.refresh_tasks[instance_id]

    def add_user_if_not_exists(self, instance_id: str, user_id: int, username: str):
        """Add user to tracking if they don't exist"""
        instance = self.get_instance(instance_id)
        if not instance:
            return

        if 'users' not in instance:
            instance['users'] = {}

        if str(user_id) not in instance['users']:
            instance['users'][str(user_id)] = {
                'username': username,
                'status': 'ended',
                'last_action': None,
                'pause_end': None,
                'pause_duration': None
            }
            for i, inst in enumerate(self.instances['instances']):
                if inst.get('instance_id') == instance_id:
                    self.instances['instances'][i] = instance
                    break
            self.save_instances()

    def update_user_status(self, instance_id: str, user_id: int, status: str, **kwargs):
        """Update user status"""
        instance = self.get_instance(instance_id)
        if not instance or 'users' not in instance:
            return

        user_key = str(user_id)
        if user_key in instance['users']:
            instance['users'][user_key]['status'] = status
            instance['users'][user_key]['last_action'] = datetime.now().isoformat()

            for key, value in kwargs.items():
                instance['users'][user_key][key] = value

            for i, inst in enumerate(self.instances['instances']):
                if inst.get('instance_id') == instance_id:
                    self.instances['instances'][i] = instance
                    break
            self.save_instances()

            asyncio.create_task(self.refresh_admin_panel_now(instance_id))

    async def refresh_admin_panel_now(self, instance_id: str):
        """Immediately refresh the admin panel after a status change"""
        try:
            if not self.bot:
                return

            instance = self.get_instance(instance_id)
            if not instance or 'admin_message_id' not in instance:
                return

            admin_channel = self.bot.get_channel(instance['admin_channel'])
            if not admin_channel:
                return

            admin_message = await admin_channel.fetch_message(instance['admin_message_id'])
            current_page = instance.get('admin_page', 0)
            new_embed = self.create_status_embed(instance_id, page=current_page)
            admin_view = AdminPanelView(self, instance_id, page=current_page)
            await admin_message.edit(embed=new_embed, view=admin_view)
        except Exception as e:
            print(f"Error refreshing admin panel immediately: {e}")

    def update_admin_page(self, instance_id: str, page: int):
        """Update the current admin page"""
        instance = self.get_instance(instance_id)
        if instance:
            instance['admin_page'] = page
            for i, inst in enumerate(self.instances['instances']):
                if inst.get('instance_id') == instance_id:
                    self.instances['instances'][i] = instance
                    break
            self.save_instances()

    async def start_pause_timer(self, bot, instance_id: str, user_id: int, duration_minutes: int):
        """Start a pause timer for a user"""
        if (instance_id, user_id) in self.pause_tasks:
            self.pause_tasks[(instance_id, user_id)].cancel()

        async def pause_timer():
            await asyncio.sleep(duration_minutes * 60)

            user = await bot.fetch_user(user_id)
            if user:
                try:
                    embed = discord.Embed(
                        title="⏰ Pause terminée",
                        description=f"Ta pause de {duration_minutes} minutes est terminée !\nClique sur le bouton pour confirmer que tu reprends ton shift.",
                        color=discord.Color.from_rgb(255, 255, 255)
                    )
                    view = ConfirmResumeView(self, instance_id, user_id)
                    await user.send(embed=embed, view=view)
                except Exception as e:
                    print(f"Error sending pause end DM: {e}")
                    # Fallback: repasser en active automatiquement si le DM ne passe pas
                    self.update_user_status(instance_id, user_id, 'active', pause_end=None, pause_duration=None)

            if (instance_id, user_id) in self.pause_tasks:
                del self.pause_tasks[(instance_id, user_id)]

        task = asyncio.create_task(pause_timer())
        self.pause_tasks[(instance_id, user_id)] = task

    async def confirm_resume(self, instance_id: str, user_id: int):
        """Confirm user is resuming work after pause"""
        self.update_user_status(instance_id, user_id, 'active', pause_end=None, pause_duration=None)
        asyncio.create_task(self.refresh_admin_panel_now(instance_id))


    async def setup_commands(self, bot):
        """Register ActivityManager-specific commands"""
        self.bot = bot


# Confirm Resume View (for DM after pause)
class ConfirmResumeView(discord.ui.View):
    def __init__(self, manager: ActivityManager, instance_id: str, user_id: int):
        super().__init__(timeout=None)
        self.manager = manager
        self.instance_id = instance_id
        self.user_id = user_id

        # Confirm button
        confirm_button = discord.ui.Button(
            label="Confirmer reprise",
            style=discord.ButtonStyle.green,
            emoji="✅"
        )
        confirm_button.callback = self.confirm_resume
        self.add_item(confirm_button)

    async def confirm_resume(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                "❌ Ce bouton n'est pas pour toi.",
                ephemeral=True,
                delete_after=60
            )
            return

        await self.manager.confirm_resume(self.instance_id, self.user_id)

        await interaction.response.send_message(
            "✅ Tu es de retour en shift ! Bon courage ! 💪",
            ephemeral=True
        )


# Admin Panel View with Pagination
class AdminPanelView(discord.ui.View):
    def __init__(self, manager: ActivityManager, instance_id: str, page: int = 0):
        super().__init__(timeout=None)
        self.manager = manager
        self.instance_id = instance_id
        self.page = page

        instance = manager.get_instance(instance_id)
        users = instance.get('users', {}) if instance else {}
        total_users = len(users)
        total_pages = max(1, (total_users + 4) // 5)

        prev_button = discord.ui.Button(
            label="◀️ Précédent",
            style=discord.ButtonStyle.gray,
            disabled=(page == 0)
        )
        prev_button.callback = self.previous_page
        self.add_item(prev_button)

        next_button = discord.ui.Button(
            label="Suivant ▶️",
            style=discord.ButtonStyle.gray,
            disabled=(page >= total_pages - 1)
        )
        next_button.callback = self.next_page
        self.add_item(next_button)

    async def previous_page(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self.manager.update_admin_page(self.instance_id, self.page)

        new_embed = self.manager.create_status_embed(self.instance_id, page=self.page)
        new_view = AdminPanelView(self.manager, self.instance_id, page=self.page)
        await interaction.response.edit_message(embed=new_embed, view=new_view)

    async def next_page(self, interaction: discord.Interaction):
        instance = self.manager.get_instance(self.instance_id)
        users = instance.get('users', {}) if instance else {}
        total_users = len(users)
        total_pages = max(1, (total_users + 4) // 5)

        self.page = min(total_pages - 1, self.page + 1)
        self.manager.update_admin_page(self.instance_id, self.page)

        new_embed = self.manager.create_status_embed(self.instance_id, page=self.page)
        new_view = AdminPanelView(self.manager, self.instance_id, page=self.page)
        await interaction.response.edit_message(embed=new_embed, view=new_view)


# Activity Buttons View
class ActivityButtonsView(discord.ui.View):
    def __init__(self, manager: ActivityManager, instance_id: str):
        super().__init__(timeout=None)
        self.manager = manager
        self.instance_id = instance_id

    @discord.ui.button(label="Début de shift", style=discord.ButtonStyle.green, emoji="👋")
    async def start_shift(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.manager.add_user_if_not_exists(
            self.instance_id,
            interaction.user.id,
            interaction.user.name
        )

        self.manager.update_user_status(self.instance_id, interaction.user.id, 'active')

        await interaction.response.send_message(
            "✅ Je commence mon shift ! 🚀",
            ephemeral=True,
            delete_after=60
        )

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.gray, emoji="☕")
    async def take_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = PauseModal(self.manager, self.instance_id)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Fin de shift", style=discord.ButtonStyle.red, emoji="👋")
    async def end_shift(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.manager.add_user_if_not_exists(
            self.instance_id,
            interaction.user.id,
            interaction.user.name
        )

        if (self.instance_id, interaction.user.id) in self.manager.pause_tasks:
            self.manager.pause_tasks[(self.instance_id, interaction.user.id)].cancel()
            del self.manager.pause_tasks[(self.instance_id, interaction.user.id)]

        self.manager.update_user_status(self.instance_id, interaction.user.id, 'ended')

        await interaction.response.send_message(
            "✅ Mon shift est terminé, à demain ! 🙌",
            ephemeral=True,
            delete_after=60
        )


# Pause Modal
class PauseModal(discord.ui.Modal):
    def __init__(self, manager: ActivityManager, instance_id: str):
        super().__init__(title="Pause")
        self.manager = manager
        self.instance_id = instance_id

        self.duration = discord.ui.TextInput(
            label="Durée de la pause (en minutes)",
            placeholder="Ex: 15",
            required=True,
            max_length=3
        )
        self.add_item(self.duration)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            duration = int(self.duration.value)
            if duration <= 0 or duration > 999:
                await interaction.response.send_message(
                    "❌ La durée doit être entre 1 et 999 minutes.",
                    ephemeral=True,
                    delete_after=60
                )
                return

            self.manager.add_user_if_not_exists(
                self.instance_id,
                interaction.user.id,
                interaction.user.name
            )

            pause_end = (datetime.now() + timedelta(minutes=duration)).isoformat()

            self.manager.update_user_status(
                self.instance_id,
                interaction.user.id,
                'pause',
                pause_end=pause_end,
                pause_duration=duration
            )

            bot = interaction.client
            await self.manager.start_pause_timer(bot, self.instance_id, interaction.user.id, duration)

            await interaction.response.send_message(
                f"✅ Petite pause de {duration} minutes ! ☕\n"
                f"Je te rappellerai quand ce sera terminé.",
                ephemeral=True,
                delete_after=60
            )

        except ValueError:
            await interaction.response.send_message(
                "❌ Veuillez entrer un nombre valide de minutes.",
                ephemeral=True,
                delete_after=60
            )
