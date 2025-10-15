import discord
from discord import app_commands
import json
from abc import ABC, abstractmethod


class BaseTool(ABC):
    """Base class for all tool managers"""

    def __init__(self, tool_name: str, display_name: str, description: str, emoji: str, json_file: str):
        self.tool_name = tool_name
        self.display_name = display_name
        self.description = description
        self.emoji = emoji
        self.json_file = json_file
        self.instances = self.load_instances()
        self.config = self.load_config()

    def load_config(self):
        """Load bot configuration"""
        try:
            with open('config.json', 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {"allowed_user_ids": []}

    def load_instances(self):
        """Load instances from JSON file"""
        try:
            with open(self.json_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {"instances": []}

    def save_instances(self):
        """Save instances to JSON file"""
        with open(self.json_file, 'w') as f:
            json.dump(self.instances, f, indent=2)

    def add_instance(self, guild_id: int, setup_channel: int, admin_channel: int):
        """Add a new instance (checks for existing instances with same channels)"""
        import uuid

        # Check if instance already exists with same setup_channel or admin_channel
        for instance in self.instances['instances']:
            if instance.get('setup_channel') == setup_channel:
                return None, "setup_channel"  # Instance exists with this setup channel
            if instance.get('admin_channel') == admin_channel:
                return None, "admin_channel"  # Instance exists with this admin channel

        # Generate unique instance ID
        instance_id = str(uuid.uuid4())

        # Add new instance
        self.instances['instances'].append({
            'instance_id': instance_id,
            'guild_id': guild_id,
            'setup_channel': setup_channel,
            'admin_channel': admin_channel
        })
        self.save_instances()
        return instance_id, None  # Return instance_id and no error

    def get_instance(self, instance_id: str):
        """Get instance configuration by instance_id"""
        for instance in self.instances['instances']:
            if instance.get('instance_id') == instance_id:
                return instance
        return None

    def get_instance_by_channel(self, channel_id: int):
        """Get instance by setup_channel or admin_channel"""
        for instance in self.instances['instances']:
            if instance.get('setup_channel') == channel_id or instance.get('admin_channel') == channel_id:
                return instance
        return None

    def is_user_allowed(self, user_id: int) -> bool:
        """Check if a user is allowed to use restricted commands"""
        allowed_ids = self.config.get('allowed_user_ids', [])
        # If list is empty, allow everyone (for backward compatibility)
        if not allowed_ids:
            return True
        return user_id in allowed_ids

    async def check_permission(self, interaction: discord.Interaction, public: bool = False) -> bool:
        """
        Check if user has permission to run a command.

        Args:
            interaction: The Discord interaction
            public: If True, command is accessible to everyone. If False, check allowed_user_ids

        Returns:
            True if user has permission, False otherwise (and sends error message)
        """
        if public:
            return True

        if not self.is_user_allowed(interaction.user.id):
            await interaction.response.send_message(
                "❌ Vous n'avez pas la permission d'utiliser cette commande.",
                ephemeral=True,
                delete_after=60
            )
            return False
        return True

    @abstractmethod
    async def setup_commands(self, bot):
        """Register tool-specific commands - to be implemented by each tool"""
        pass

    def get_setup_modal(self):
        """Return the setup modal class for this tool"""
        from .modals import SetupModal
        return SetupModal(self)
