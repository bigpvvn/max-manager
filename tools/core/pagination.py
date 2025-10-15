import discord
from typing import List, Callable, Any, Optional


class PaginatedEmbed:
    """
    Système de pagination modulaire pour les embeds Discord.
    Garantit que le contenu ne dépasse jamais 2000 caractères par page.
    """

    def __init__(
        self,
        title: str,
        description: str = "",
        color: discord.Color = discord.Color.blue(),
        footer_text: str = "",
        items_per_page: int = 5,
        max_chars_per_page: int = 1900  # Sécurité sous la limite de 2000
    ):
        """
        Initialize paginated embed system

        Args:
            title: Titre de l'embed
            description: Description de l'embed
            color: Couleur de l'embed
            footer_text: Texte de base du footer (la pagination sera ajoutée automatiquement)
            items_per_page: Nombre maximum d'items par page (par défaut)
            max_chars_per_page: Nombre maximum de caractères par page
        """
        self.title = title
        self.description = description
        self.color = color
        self.footer_text = footer_text
        self.items_per_page = items_per_page
        self.max_chars_per_page = max_chars_per_page
        self.sections = []  # List of sections to add

    def add_section(
        self,
        name: str,
        items: List[Any],
        formatter: Callable[[Any], str],
        empty_message: str = "Aucun élément",
        inline: bool = False,
        max_items: Optional[int] = None
    ):
        """
        Ajoute une section à l'embed avec pagination automatique

        Args:
            name: Nom de la section
            items: Liste des items à afficher
            formatter: Fonction pour formatter chaque item en string
            empty_message: Message si la liste est vide
            inline: Si le field doit être inline
            max_items: Nombre maximum d'items à afficher (None = tous)
        """
        self.sections.append({
            'name': name,
            'items': items,
            'formatter': formatter,
            'empty_message': empty_message,
            'inline': inline,
            'max_items': max_items
        })

    def _calculate_embed_size(self, embed: discord.Embed) -> int:
        """Calcule la taille totale d'un embed en caractères"""
        size = len(embed.title or "")
        size += len(embed.description or "")

        for field in embed.fields:
            size += len(field.name or "")
            size += len(field.value or "")

        if embed.footer:
            size += len(embed.footer.text or "")

        return size

    def _build_section_content(self, section: dict, start_idx: int, items_count: int) -> tuple[str, int]:
        """
        Construit le contenu d'une section

        Returns:
            (content, items_used) - Le contenu formaté et le nombre d'items utilisés
        """
        items = section['items']
        formatter = section['formatter']
        max_items = section['max_items']

        if not items:
            return section['empty_message'], 0

        # Limite le nombre d'items si spécifié
        if max_items is not None:
            items = items[:max_items]

        content = ""
        items_used = 0

        # Commence à partir de start_idx
        for i in range(start_idx, min(start_idx + items_count, len(items))):
            item_text = formatter(items[i])
            content += item_text + "\n"
            items_used += 1

        # Ajoute un indicateur s'il reste des items
        remaining = len(items) - (start_idx + items_used)
        if remaining > 0:
            content += f"\n*... et {remaining} autre(s)*"

        return content.strip(), items_used

    def generate_pages(self) -> List[discord.Embed]:
        """
        Génère toutes les pages avec pagination automatique

        Returns:
            Liste d'embeds, un par page
        """
        pages = []
        current_embed = discord.Embed(
            title=self.title,
            description=self.description,
            color=self.color
        )

        # Si pas de sections, retourne un embed vide
        if not self.sections:
            pages.append(current_embed)
            return pages

        section_indices = [0] * len(self.sections)  # Track position in each section
        sections_completed = [False] * len(self.sections)

        while not all(sections_completed):
            page_created = False

            for section_idx, section in enumerate(self.sections):
                if sections_completed[section_idx]:
                    continue

                start_idx = section_indices[section_idx]
                items_remaining = len(section['items']) - start_idx

                if items_remaining <= 0:
                    sections_completed[section_idx] = True
                    continue

                # Essaye d'ajouter des items de cette section
                items_to_try = min(self.items_per_page, items_remaining)

                while items_to_try > 0:
                    content, items_used = self._build_section_content(
                        section,
                        start_idx,
                        items_to_try
                    )

                    # Créer un embed temporaire pour tester la taille
                    test_embed = current_embed.copy()
                    test_embed.add_field(
                        name=section['name'],
                        value=content,
                        inline=section['inline']
                    )

                    # Vérifie la taille
                    if self._calculate_embed_size(test_embed) <= self.max_chars_per_page:
                        # Ça rentre ! Ajoute le field
                        current_embed.add_field(
                            name=section['name'],
                            value=content,
                            inline=section['inline']
                        )
                        section_indices[section_idx] += items_used
                        page_created = True

                        # Si on a tout affiché de cette section
                        if section_indices[section_idx] >= len(section['items']):
                            sections_completed[section_idx] = True
                        break
                    else:
                        # Trop grand, réduis le nombre d'items
                        items_to_try = max(1, items_to_try // 2)

                        # Si même avec 1 item ça ne rentre pas
                        if items_to_try == 1:
                            # Si l'embed est vide, on prend l'item quand même (tronqué)
                            if len(current_embed.fields) == 0:
                                content = content[:1500] + "... (tronqué)"
                                current_embed.add_field(
                                    name=section['name'],
                                    value=content,
                                    inline=section['inline']
                                )
                                section_indices[section_idx] += 1
                                page_created = True
                            # Sinon on arrête et crée une nouvelle page
                            break
                        elif items_to_try < 1:
                            # On ne peut plus réduire, nouvelle page
                            break

            # Si on a créé du contenu ou qu'il faut créer une nouvelle page
            if len(current_embed.fields) > 0:
                pages.append(current_embed)
                current_embed = discord.Embed(
                    title=self.title,
                    description=self.description,
                    color=self.color
                )
            elif not page_created:
                # Aucun progrès fait, on arrête pour éviter une boucle infinie
                break

        # Ajoute les footers avec numéros de page
        total_pages = len(pages)
        for i, page in enumerate(pages):
            footer = self.footer_text
            if total_pages > 1:
                footer += f" | Page {i + 1}/{total_pages}"
            page.set_footer(text=footer)
            page.timestamp = discord.utils.utcnow()

        return pages if pages else [current_embed]


class PaginationView(discord.ui.View):
    """Vue avec boutons de navigation pour la pagination"""

    def __init__(
        self,
        pages: List[discord.Embed],
        current_page: int = 0,
        timeout: Optional[float] = None,
        extra_buttons: Optional[List[discord.ui.Button]] = None
    ):
        """
        Initialize pagination view

        Args:
            pages: Liste des embeds (pages)
            current_page: Page actuelle (0-indexed)
            timeout: Timeout pour les boutons (None = pas de timeout)
            extra_buttons: Boutons supplémentaires à ajouter
        """
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current_page = max(0, min(current_page, len(pages) - 1))
        self.total_pages = len(pages)

        # Ajoute les boutons de navigation
        self._add_navigation_buttons()

        # Ajoute les boutons supplémentaires si fournis
        if extra_buttons:
            for button in extra_buttons:
                self.add_item(button)

    def _add_navigation_buttons(self):
        """Ajoute les boutons de navigation"""
        # Bouton précédent
        prev_button = discord.ui.Button(
            label="◀️ Précédent",
            style=discord.ButtonStyle.gray,
            disabled=(self.current_page == 0),
            custom_id="prev"
        )
        prev_button.callback = self._previous_page
        self.add_item(prev_button)

        # Bouton suivant
        next_button = discord.ui.Button(
            label="Suivant ▶️",
            style=discord.ButtonStyle.gray,
            disabled=(self.current_page >= self.total_pages - 1),
            custom_id="next"
        )
        next_button.callback = self._next_page
        self.add_item(next_button)

    async def _previous_page(self, interaction: discord.Interaction):
        """Aller à la page précédente"""
        self.current_page = max(0, self.current_page - 1)
        await self._update_message(interaction)

    async def _next_page(self, interaction: discord.Interaction):
        """Aller à la page suivante"""
        self.current_page = min(self.total_pages - 1, self.current_page + 1)
        await self._update_message(interaction)

    async def _update_message(self, interaction: discord.Interaction):
        """Met à jour le message avec la nouvelle page"""
        # Crée une nouvelle vue avec la page mise à jour
        new_view = PaginationView(
            pages=self.pages,
            current_page=self.current_page,
            timeout=self.timeout
        )

        await interaction.response.edit_message(
            embed=self.pages[self.current_page],
            view=new_view
        )

    def get_current_embed(self) -> discord.Embed:
        """Retourne l'embed de la page actuelle"""
        return self.pages[self.current_page]


def create_simple_paginated_view(
    title: str,
    items: List[Any],
    formatter: Callable[[Any], str],
    items_per_page: int = 5,
    color: discord.Color = discord.Color.blue(),
    empty_message: str = "Aucun élément",
    footer_text: str = "",
    current_page: int = 0
) -> tuple[discord.Embed, PaginationView]:
    """
    Fonction helper pour créer rapidement une vue paginée simple

    Args:
        title: Titre de l'embed
        items: Liste des items à paginer
        formatter: Fonction pour formatter chaque item
        items_per_page: Items par page
        color: Couleur de l'embed
        empty_message: Message si liste vide
        footer_text: Texte du footer
        current_page: Page initiale

    Returns:
        (embed, view) - L'embed de la page actuelle et la vue avec boutons
    """
    paginated = PaginatedEmbed(
        title=title,
        color=color,
        footer_text=footer_text,
        items_per_page=items_per_page
    )

    paginated.add_section(
        name="",
        items=items,
        formatter=formatter,
        empty_message=empty_message
    )

    pages = paginated.generate_pages()
    view = PaginationView(pages=pages, current_page=current_page, timeout=None)

    return view.get_current_embed(), view
