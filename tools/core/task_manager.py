import discord
from discord import app_commands
from .base_tool import BaseTool
from .pagination import PaginatedEmbed, PaginationView
import asyncio
from datetime import datetime, time, timedelta
import uuid


class TaskManager(BaseTool):
    """Task Manager - Manages tasks/todos with daily recurring tasks"""

    def __init__(self):
        super().__init__(
            tool_name="task",
            display_name="Todo",
            description="Gérer les tâches",
            emoji="✅",
            json_file="tools/data/task_manager.json"
        )
        self.refresh_tasks = {}  # Store auto-refresh tasks: {instance_id: task}
        self.daily_tasks = {}  # Store daily task schedulers: {instance_id: task}
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
            title="✅ TODO — Gestion des tâches",
            description=(
                "👉 *Ce salon te permet de gérer tes tâches facilement.*\n"
                "Les nouvelles tâches apparaîtront ici. Utilise les boutons ci-dessous pour mettre à jour leur statut :\n\n"
                "- **⏳ En cours** : *indique que tu travailles dessus*\n"
                "- **✅ Fini** : *marque la tâche comme terminée*"
            ),
            color=discord.Color.from_rgb(255, 255, 255)
        )
        await setup_channel.send(embed=setup_embed)

        # Admin channel - dashboard
        admin_embed = self.create_admin_embed(instance_id, page=0)
        admin_view = AdminPanelView(self, instance_id, page=0)
        admin_message = await admin_channel.send(embed=admin_embed, view=admin_view)

        # Initialize instance data
        instance = self.get_instance(instance_id)
        if instance:
            if 'tasks' not in instance:
                instance['tasks'] = []
            if 'daily_reset_time' not in instance:
                instance['daily_reset_time'] = "00:00"  # Default midnight
            instance['admin_message_id'] = admin_message.id
            instance['admin_page'] = 0
            for i, inst in enumerate(self.instances['instances']):
                if inst.get('instance_id') == instance_id:
                    self.instances['instances'][i] = instance
                    break
            self.save_instances()

        # Start auto-refresh
        if instance_id in self.refresh_tasks:
            self.refresh_tasks[instance_id].cancel()
        refresh_task = asyncio.create_task(self.auto_refresh_admin_panel(bot, instance_id, admin_channel_id))
        self.refresh_tasks[instance_id] = refresh_task

        # Start daily task scheduler
        if instance_id in self.daily_tasks:
            self.daily_tasks[instance_id].cancel()
        daily_task = asyncio.create_task(self.daily_task_scheduler(bot, instance_id))
        self.daily_tasks[instance_id] = daily_task

        return True

    def create_admin_embed(self, instance_id: str, page: int = 0) -> discord.Embed:
        """Create the admin dashboard embed with PaginatedEmbed"""
        instance = self.get_instance(instance_id)
        tasks = instance.get('tasks', []) if instance else []
        daily_reset_time = instance.get('daily_reset_time', '00:00') if instance else '00:00'

        # Separate tasks by type
        daily_tasks = [t for t in tasks if t.get('is_daily', False)]
        specific_tasks = [t for t in tasks if not t.get('is_daily', False)]

        # Filter specific tasks by status (no done tasks)
        specific_in_progress = [t for t in specific_tasks if t['status'] == 'in_progress']
        specific_pending = [t for t in specific_tasks if t['status'] == 'pending']

        # Daily tasks (show all regardless of status)
        daily_in_progress = [t for t in daily_tasks if t['status'] == 'in_progress']
        daily_pending = [t for t in daily_tasks if t['status'] == 'pending']

        # Combine daily tasks by status
        daily_combined = []
        if daily_in_progress:
            daily_combined.append(('in_progress', daily_in_progress))
        if daily_pending:
            daily_combined.append(('pending', daily_pending))

        # Combine specific tasks by status
        specific_combined = []
        if specific_in_progress:
            specific_combined.append(('in_progress', specific_in_progress))
        if specific_pending:
            specific_combined.append(('pending', specific_pending))

        def format_daily_task(task_data):
            status, task_list = task_data
            status_labels = {
                'in_progress': '⏳ **En cours**',
                'pending': '⏸️ **En attente**'
            }

            result = f"{status_labels.get(status, 'Inconnu')} ({len(task_list)})\n"
            for task in task_list:
                content_preview = task['content'][:50]
                if len(task['content']) > 50:
                    content_preview += "..."
                result += f"• `{task['task_id'][:8]}` {content_preview}\n"
            return result

        def format_specific_task(task_data):
            status, task_list = task_data
            status_labels = {
                'in_progress': '⏳ **En cours**',
                'pending': '⏸️ **En attente**'
            }

            result = f"{status_labels.get(status, 'Inconnu')} ({len(task_list)})\n"
            for task in task_list:
                date_str = task.get('date', 'Aucune date')
                content_preview = task['content'][:50]
                if len(task['content']) > 50:
                    content_preview += "..."
                result += f"• `{task['task_id'][:8]}` [{date_str}] {content_preview}\n"
            return result

        # Create PaginatedEmbed
        paginated = PaginatedEmbed(
            title="✅ Todo",
            description=f"Tableau de bord des tâches\n🕐 Heure de réinitialisation : **{daily_reset_time}**",
            color=discord.Color.from_rgb(255, 255, 255),
            footer_text="Mise à jour automatique toutes les 60s",
            items_per_page=10,
            max_chars_per_page=1900
        )

        # Add daily tasks section
        paginated.add_section(
            name="🔄 **Tâches Journalières**",
            items=daily_combined,
            formatter=format_daily_task,
            empty_message="*Aucune tâche journalière*",
            inline=False
        )

        # Add specific tasks section
        paginated.add_section(
            name="📌 **Tâches Spécifiques**",
            items=specific_combined,
            formatter=format_specific_task,
            empty_message="*Aucune tâche spécifique*",
            inline=False
        )

        pages = paginated.generate_pages()

        # Ensure requested page exists
        page = max(0, min(page, len(pages) - 1))

        return pages[page]

    async def daily_task_scheduler(self, bot, instance_id: str):
        """Schedule daily task reset at configured time"""
        await bot.wait_until_ready()

        while not bot.is_closed():
            try:
                instance = self.get_instance(instance_id)
                if not instance:
                    break

                # Get reset time (format: "HH:MM")
                reset_time_str = instance.get('daily_reset_time', '00:00')
                hour, minute = map(int, reset_time_str.split(':'))

                # Calculate next reset time
                now = datetime.now()
                next_reset = datetime.combine(now.date(), time(hour, minute))
                if next_reset <= now:
                    next_reset += timedelta(days=1)

                # Wait until next reset
                wait_seconds = (next_reset - now).total_seconds()
                await asyncio.sleep(wait_seconds)

                # Reset daily tasks
                await self.reset_daily_tasks(bot, instance_id)

            except Exception as e:
                print(f"Error in daily task scheduler for instance {instance_id}: {e}")
                await asyncio.sleep(3600)  # Wait 1 hour on error

        if instance_id in self.daily_tasks:
            del self.daily_tasks[instance_id]

    async def reset_daily_tasks(self, bot, instance_id: str):
        """Reset all daily tasks (set back to pending and resend to setup channel)"""
        instance = self.get_instance(instance_id)
        if not instance:
            return

        setup_channel = bot.get_channel(instance['setup_channel'])
        if not setup_channel:
            return

        tasks = instance.get('tasks', [])
        for task in tasks:
            if task.get('is_daily', False):
                # Delete old message if exists
                if task.get('message_id'):
                    try:
                        old_message = await setup_channel.fetch_message(task['message_id'])
                        await old_message.delete()
                    except:
                        pass

                # Reset task status
                task['status'] = 'pending'
                task['started_at'] = None
                task['completed_at'] = None

                # Send new task card
                task_embed = self.create_task_card_embed(task)
                view = TaskCardView(self, instance_id, task['task_id'])
                message = await setup_channel.send(content="@everyone", embed=task_embed, view=view)
                task['message_id'] = message.id

        # Save changes
        for i, inst in enumerate(self.instances['instances']):
            if inst.get('instance_id') == instance_id:
                self.instances['instances'][i] = instance
                break
        self.save_instances()

        # Refresh admin panel
        await self.refresh_admin_panel_now(instance_id)

    def create_task_card_embed(self, task: dict) -> discord.Embed:
        """Create task card embed for setup channel"""
        status_colors = {
            'pending': discord.Color.light_grey(),
            'in_progress': discord.Color.orange(),
            'done': discord.Color.green()
        }

        embed = discord.Embed(
            title="📋 Tâche",
            description=task['content'],
            color=status_colors.get(task['status'], discord.Color.greyple())
        )

        # Only show date for specific tasks (no status displayed)
        if not task.get('is_daily', False) and task.get('date'):
            embed.add_field(
                name="Date",
                value=task['date'],
                inline=True
            )

        return embed

    async def add_task(self, bot, instance_id: str, content: str, user_id: int, is_daily: bool = False, date: str = None):
        """Add a new task"""
        instance = self.get_instance(instance_id)
        if not instance:
            return None

        if 'tasks' not in instance:
            instance['tasks'] = []

        task_id = str(uuid.uuid4())
        task = {
            'task_id': task_id,
            'content': content,
            'status': 'pending',
            'created_at': datetime.now().isoformat(),
            'created_by': user_id,
            'started_at': None,
            'completed_at': None,
            'message_id': None,
            'is_daily': is_daily,
            'date': date
        }

        # Send to setup channel
        setup_channel = bot.get_channel(instance['setup_channel'])
        if setup_channel:
            task_embed = self.create_task_card_embed(task)
            view = TaskCardView(self, instance_id, task_id)
            message = await setup_channel.send(content="@everyone", embed=task_embed, view=view)
            task['message_id'] = message.id

        instance['tasks'].append(task)

        for i, inst in enumerate(self.instances['instances']):
            if inst.get('instance_id') == instance_id:
                self.instances['instances'][i] = instance
                break
        self.save_instances()

        await self.refresh_admin_panel_now(instance_id)
        return task_id

    async def update_task_status(self, bot, instance_id: str, task_id: str, new_status: str):
        """Update task status"""
        instance = self.get_instance(instance_id)
        if not instance or 'tasks' not in instance:
            return False

        task = next((t for t in instance['tasks'] if t['task_id'] == task_id), None)
        if not task:
            return False

        # Update status
        old_status = task['status']
        task['status'] = new_status

        if new_status == 'in_progress' and not task.get('started_at'):
            task['started_at'] = datetime.now().isoformat()
        elif new_status == 'done':
            task['completed_at'] = datetime.now().isoformat()

        # Save changes first
        for i, inst in enumerate(self.instances['instances']):
            if inst.get('instance_id') == instance_id:
                self.instances['instances'][i] = instance
                break
        self.save_instances()

        # Then update the message
        if new_status == 'done':
            # Delete the task card from setup channel
            if task.get('message_id'):
                setup_channel = bot.get_channel(instance['setup_channel'])
                if setup_channel:
                    try:
                        message = await setup_channel.fetch_message(task['message_id'])
                        await message.delete()
                    except Exception as e:
                        print(f"Error deleting task card: {e}")

            # Remove task from list if it's not daily (daily tasks stay for next reset)
            if not task.get('is_daily', False):
                instance['tasks'].remove(task)
                # Save again after removing task
                for i, inst in enumerate(self.instances['instances']):
                    if inst.get('instance_id') == instance_id:
                        self.instances['instances'][i] = instance
                        break
                self.save_instances()
        else:
            # Update the task card embed
            if task.get('message_id'):
                setup_channel = bot.get_channel(instance['setup_channel'])
                if setup_channel:
                    try:
                        message = await setup_channel.fetch_message(task['message_id'])
                        new_embed = self.create_task_card_embed(task)
                        # Hide "En cours" button if task is in progress
                        show_in_progress = (new_status != 'in_progress')
                        view = TaskCardView(self, instance_id, task_id, show_in_progress=show_in_progress)
                        await message.edit(embed=new_embed, view=view)
                        print(f"Successfully updated task card from {old_status} to {new_status}")
                    except Exception as e:
                        print(f"Error updating task card embed: {e}")

        await self.refresh_admin_panel_now(instance_id)
        return True

    async def delete_task(self, bot, instance_id: str, task_id: str):
        """Delete a task"""
        instance = self.get_instance(instance_id)
        if not instance or 'tasks' not in instance:
            return False

        task = next((t for t in instance['tasks'] if t['task_id'].startswith(task_id)), None)
        if not task:
            return False

        # Delete message from setup channel
        if task.get('message_id'):
            try:
                setup_channel = bot.get_channel(instance['setup_channel'])
                if setup_channel:
                    message = await setup_channel.fetch_message(task['message_id'])
                    await message.delete()
            except:
                pass

        instance['tasks'].remove(task)

        for i, inst in enumerate(self.instances['instances']):
            if inst.get('instance_id') == instance_id:
                self.instances['instances'][i] = instance
                break
        self.save_instances()

        await self.refresh_admin_panel_now(instance_id)
        return True

    async def set_daily_reset_time(self, instance_id: str, reset_time: str):
        """Set the daily reset time (format: HH:MM)"""
        instance = self.get_instance(instance_id)
        if not instance:
            return False

        instance['daily_reset_time'] = reset_time

        for i, inst in enumerate(self.instances['instances']):
            if inst.get('instance_id') == instance_id:
                self.instances['instances'][i] = instance
                break
        self.save_instances()

        # Restart scheduler with new time
        if instance_id in self.daily_tasks:
            self.daily_tasks[instance_id].cancel()
        if self.bot:
            admin_channel_id = instance.get('admin_channel')
            daily_task = asyncio.create_task(self.daily_task_scheduler(self.bot, instance_id))
            self.daily_tasks[instance_id] = daily_task

        await self.refresh_admin_panel_now(instance_id)
        return True

    async def auto_refresh_admin_panel(self, bot, instance_id: str, admin_channel_id: int):
        """Auto-refresh admin panel every 60 seconds"""
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
                    new_embed = self.create_admin_embed(instance_id, page=current_page)
                    admin_view = AdminPanelView(self, instance_id, page=current_page)
                    await admin_message.edit(embed=new_embed, view=admin_view)
                except discord.NotFound:
                    new_embed = self.create_admin_embed(instance_id, page=0)
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
                print(f"Error refreshing todo admin panel for instance {instance_id}: {e}")

            await asyncio.sleep(60)

        if instance_id in self.refresh_tasks:
            del self.refresh_tasks[instance_id]

    async def refresh_admin_panel_now(self, instance_id: str):
        """Immediately refresh the admin panel"""
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
            new_embed = self.create_admin_embed(instance_id, page=current_page)
            admin_view = AdminPanelView(self, instance_id, page=current_page)
            await admin_message.edit(embed=new_embed, view=admin_view)
        except Exception as e:
            print(f"Error refreshing todo admin panel immediately: {e}")

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


    async def setup_commands(self, bot):
        """Register TaskManager-specific commands"""
        self.bot = bot


# Task Card View (for setup channel)
class TaskCardView(discord.ui.View):
    def __init__(self, manager: TaskManager, instance_id: str, task_id: str, show_in_progress: bool = True):
        super().__init__(timeout=None)
        self.manager = manager
        self.instance_id = instance_id
        self.task_id = task_id

        # Add "En cours" button only if show_in_progress is True
        if show_in_progress:
            in_progress_button = discord.ui.Button(
                label="En cours",
                style=discord.ButtonStyle.gray,
                emoji="⏳"
            )
            in_progress_button.callback = self.in_progress_callback
            self.add_item(in_progress_button)

        # Always add "Fini" button
        done_button = discord.ui.Button(
            label="Fini",
            style=discord.ButtonStyle.green,
            emoji="✅"
        )
        done_button.callback = self.done_callback
        self.add_item(done_button)

    async def in_progress_callback(self, interaction: discord.Interaction):
        bot = interaction.client
        success = await self.manager.update_task_status(
            bot,
            self.instance_id,
            self.task_id,
            'in_progress'
        )

        if success:
            await interaction.response.send_message("⏳ Tâche marquée en cours !", ephemeral=True, delete_after=60)
        else:
            await interaction.response.send_message("❌ Erreur lors de la mise à jour.", ephemeral=True, delete_after=60)

    async def done_callback(self, interaction: discord.Interaction):
        bot = interaction.client
        success = await self.manager.update_task_status(
            bot,
            self.instance_id,
            self.task_id,
            'done'
        )

        if success:
            await interaction.response.send_message("✅ Tâche marquée comme terminée !", ephemeral=True, delete_after=60)
        else:
            await interaction.response.send_message("❌ Erreur lors de la mise à jour.", ephemeral=True, delete_after=60)


# Admin Panel View
class AdminPanelView(discord.ui.View):
    def __init__(self, manager: TaskManager, instance_id: str, page: int = 0):
        super().__init__(timeout=None)
        self.manager = manager
        self.instance_id = instance_id
        self.page = page

        # Add Task button
        add_button = discord.ui.Button(
            label="Ajouter",
            style=discord.ButtonStyle.primary,
            emoji="➕"
        )
        add_button.callback = self.add_task
        self.add_item(add_button)

        # Delete Task button
        delete_button = discord.ui.Button(
            label="Supprimer",
            style=discord.ButtonStyle.danger,
            emoji="🗑️"
        )
        delete_button.callback = self.delete_task
        self.add_item(delete_button)

        # Set Reset Time button
        time_button = discord.ui.Button(
            label="Heure de réinit",
            style=discord.ButtonStyle.secondary,
            emoji="🕐"
        )
        time_button.callback = self.set_reset_time
        self.add_item(time_button)

        # View Daily Tasks button
        view_daily_button = discord.ui.Button(
            label="Voir tâches journalières",
            style=discord.ButtonStyle.secondary,
            emoji="🔄"
        )
        view_daily_button.callback = self.view_daily_tasks
        self.add_item(view_daily_button)

    async def add_task(self, interaction: discord.Interaction):
        if not self.manager.is_user_allowed(interaction.user.id):
            await interaction.response.send_message(
                "❌ Vous n'avez pas la permission d'ajouter des tâches.",
                ephemeral=True,
                delete_after=60
            )
            return

        view = TaskTypeSelectView(self.manager, self.instance_id)
        await interaction.response.send_message(
            "Sélectionnez le type de tâche :",
            view=view,
            ephemeral=True,
            delete_after=60
        )

    async def delete_task(self, interaction: discord.Interaction):
        if not self.manager.is_user_allowed(interaction.user.id):
            await interaction.response.send_message(
                "❌ Vous n'avez pas la permission de supprimer des tâches.",
                ephemeral=True,
                delete_after=60
            )
            return

        modal = DeleteTaskModal(self.manager, self.instance_id)
        await interaction.response.send_modal(modal)

    async def set_reset_time(self, interaction: discord.Interaction):
        if not self.manager.is_user_allowed(interaction.user.id):
            await interaction.response.send_message(
                "❌ Vous n'avez pas la permission de modifier l'heure de réinitialisation.",
                ephemeral=True,
                delete_after=60
            )
            return

        modal = SetResetTimeModal(self.manager, self.instance_id)
        await interaction.response.send_modal(modal)

    async def view_daily_tasks(self, interaction: discord.Interaction):
        if not self.manager.is_user_allowed(interaction.user.id):
            await interaction.response.send_message(
                "❌ Vous n'avez pas la permission de voir les tâches journalières.",
                ephemeral=True,
                delete_after=60
            )
            return

        instance = self.manager.get_instance(self.instance_id)
        if not instance:
            await interaction.response.send_message(
                "❌ Instance introuvable.",
                ephemeral=True,
                delete_after=60
            )
            return

        tasks = instance.get('tasks', [])
        daily_tasks = [t for t in tasks if t.get('is_daily', False)]

        if not daily_tasks:
            await interaction.response.send_message(
                "Aucune tâche journalière trouvée.",
                ephemeral=True,
                delete_after=60
            )
            return

        # Create embed with all daily tasks
        embed = discord.Embed(
            title="🔄 Tâches Journalières",
            description="Liste complète des tâches journalières",
            color=discord.Color.from_rgb(255, 255, 255)
        )

        for task in daily_tasks:
            content_preview = task['content'][:100]
            if len(task['content']) > 100:
                content_preview += "..."

            embed.add_field(
                name=f"`{task['task_id'][:8]}`",
                value=content_preview,
                inline=False
            )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
            delete_after=60
        )


# Task Type Select View
class TaskTypeSelectView(discord.ui.View):
    def __init__(self, manager: TaskManager, instance_id: str):
        super().__init__(timeout=60)
        self.manager = manager
        self.instance_id = instance_id

        select = discord.ui.Select(
            placeholder="Choisissez le type de tâche...",
            options=[
                discord.SelectOption(
                    label="Tâche Spécifique",
                    description="Tâche unique avec une date",
                    value="specific",
                    emoji="📌"
                ),
                discord.SelectOption(
                    label="Tâche Journalière",
                    description="Se répète chaque jour automatiquement",
                    value="daily",
                    emoji="🔄"
                )
            ]
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        task_type = self.children[0].values[0]

        if task_type == "specific":
            modal = AddSpecificTaskModal(self.manager, self.instance_id)
        else:
            modal = AddDailyTaskModal(self.manager, self.instance_id)

        await interaction.response.send_modal(modal)


# Add Specific Task Modal
class AddSpecificTaskModal(discord.ui.Modal):
    def __init__(self, manager: TaskManager, instance_id: str):
        super().__init__(title="Ajouter une tâche spécifique")
        self.manager = manager
        self.instance_id = instance_id

        self.content = discord.ui.TextInput(
            label="Description de la tâche",
            placeholder="Ex: Préparer le rapport mensuel",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=500
        )
        self.add_item(self.content)

        self.date = discord.ui.TextInput(
            label="Date (format: JJ/MM/YYYY)",
            placeholder="Ex: 25/12/2024",
            required=True,
            max_length=10
        )
        self.add_item(self.date)

    async def on_submit(self, interaction: discord.Interaction):
        bot = interaction.client
        task_id = await self.manager.add_task(
            bot,
            self.instance_id,
            self.content.value,
            interaction.user.id,
            is_daily=False,
            date=self.date.value
        )

        if task_id:
            await interaction.response.send_message(
                f"✅ Tâche spécifique ajoutée avec succès !",
                ephemeral=True,
                delete_after=60
            )
        else:
            await interaction.response.send_message(
                "❌ Erreur lors de l'ajout de la tâche.",
                ephemeral=True,
                delete_after=60
            )


# Add Daily Task Modal
class AddDailyTaskModal(discord.ui.Modal):
    def __init__(self, manager: TaskManager, instance_id: str):
        super().__init__(title="Ajouter une tâche journalière")
        self.manager = manager
        self.instance_id = instance_id

        self.content = discord.ui.TextInput(
            label="Description de la tâche",
            placeholder="Ex: Vérifier les emails",
            required=True,
            style=discord.TextStyle.paragraph,
            max_length=500
        )
        self.add_item(self.content)

    async def on_submit(self, interaction: discord.Interaction):
        bot = interaction.client
        task_id = await self.manager.add_task(
            bot,
            self.instance_id,
            self.content.value,
            interaction.user.id,
            is_daily=True,
            date=None
        )

        if task_id:
            await interaction.response.send_message(
                f"✅ Tâche journalière ajoutée avec succès !\n"
                f"Elle se réinitialisera automatiquement chaque jour.",
                ephemeral=True,
                delete_after=60
            )
        else:
            await interaction.response.send_message(
                "❌ Erreur lors de l'ajout de la tâche.",
                ephemeral=True,
                delete_after=60
            )


# Delete Task Modal
class DeleteTaskModal(discord.ui.Modal):
    def __init__(self, manager: TaskManager, instance_id: str):
        super().__init__(title="Supprimer une tâche")
        self.manager = manager
        self.instance_id = instance_id

        self.task_id = discord.ui.TextInput(
            label="ID de la tâche (8 caractères)",
            placeholder="Ex: a1b2c3d4",
            required=True,
            max_length=8
        )
        self.add_item(self.task_id)

    async def on_submit(self, interaction: discord.Interaction):
        bot = interaction.client
        success = await self.manager.delete_task(
            bot,
            self.instance_id,
            self.task_id.value
        )

        if success:
            await interaction.response.send_message(
                "✅ Tâche supprimée avec succès !",
                ephemeral=True,
                delete_after=60
            )
        else:
            await interaction.response.send_message(
                "❌ Tâche introuvable ou erreur lors de la suppression.",
                ephemeral=True,
                delete_after=60
            )


# Set Reset Time Modal
class SetResetTimeModal(discord.ui.Modal):
    def __init__(self, manager: TaskManager, instance_id: str):
        super().__init__(title="Définir l'heure de réinitialisation")
        self.manager = manager
        self.instance_id = instance_id

        self.reset_time = discord.ui.TextInput(
            label="Heure (format: HH:MM)",
            placeholder="Ex: 00:00 ou 06:30",
            required=True,
            max_length=5
        )
        self.add_item(self.reset_time)

    async def on_submit(self, interaction: discord.Interaction):
        # Validate time format
        try:
            hour, minute = map(int, self.reset_time.value.split(':'))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
        except:
            await interaction.response.send_message(
                "❌ Format invalide. Utilisez HH:MM (ex: 00:00 ou 14:30)",
                ephemeral=True,
                delete_after=60
            )
            return

        success = await self.manager.set_daily_reset_time(
            self.instance_id,
            self.reset_time.value
        )

        if success:
            await interaction.response.send_message(
                f"✅ Heure de réinitialisation définie à **{self.reset_time.value}** !",
                ephemeral=True,
                delete_after=60
            )
        else:
            await interaction.response.send_message(
                "❌ Erreur lors de la configuration.",
                ephemeral=True,
                delete_after=60
            )
