from enum import Enum
from typing import Dict, Union, List, Optional, Any

from pydantic import BaseModel, field_validator


class Template(str, Enum):
    """Supported presentation templates"""

    DEFAULT = "default"
    GRADIENT = "gradient"
    ADAM = "adam"
    BRUNO = "bruno"
    CLYDE = "clyde"
    DANIEL = "daniel"
    EDDY = "eddy"
    FELIX = "felix"
    IRIS = "iris"
    MONOLITH = "monolith"
    NEXUS = "nexus"
    AURORA = "aurora"
    LAVENDER = "lavender"
    NEBULA = "nebula"
    MARINA = "marina"
    MONARCH = "monarch"
    SERENE = "serene"

    @classmethod
    def get_all_values(cls) -> List[str]:
        """Get all template values as a list"""
        return [template.value for template in cls]

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Check if a value is a valid template"""
        return value in cls.get_all_values()


class Tone(str, Enum):
    """Supported presentation tones"""

    DEFAULT = "default"
    CASUAL = "casual"
    PROFESSIONAL = "professional"
    FUNNY = "funny"
    EDUCATIONAL = "educational"
    SALES_PITCH = "sales_pitch"

    @classmethod
    def get_all_values(cls) -> List[str]:
        """Get all tone values as a list"""
        return [tone.value for tone in cls]

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Check if a value is a valid tone"""
        return value in cls.get_all_values()


class Verbosity(str, Enum):
    """Supported presentation verbosity levels"""

    CONCISE = "concise"
    STANDARD = "standard"
    TEXT_HEAVY = "text-heavy"

    @classmethod
    def get_all_values(cls) -> List[str]:
        """Get all verbosity values as a list"""
        return [verbosity.value for verbosity in cls]

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Check if a value is a valid verbosity"""
        return value in cls.get_all_values()


class ResponseFormat(str, Enum):
    """Supported response formats"""

    POWERPOINT = "powerpoint"
    PDF = "pdf"

    @classmethod
    def get_all_values(cls) -> List[str]:
        """Get all response format values as a list"""
        return [format.value for format in cls]

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Check if a value is a valid response format"""
        return value in cls.get_all_values()


class TaskState(str, Enum):
    """Task states as defined by the SlideSpeak API"""

    FAILURE = "FAILURE"
    SUCCESS = "SUCCESS"
    SENT = "SENT"

    @classmethod
    def get_all_values(cls) -> List[str]:
        """Get all task state values as a list"""
        return [state.value for state in cls]

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Check if a value is a valid task state"""
        return value in cls.get_all_values()


class Layout(str, Enum):
    """Supported slide layouts as defined by the SlideSpeak API"""

    ITEMS = "items"
    STEPS = "steps"
    SUMMARY = "summary"
    COMPARISON = "comparison"
    BIG_NUMBER = "big-number"
    MILESTONE = "milestone"
    PESTEL = "pestel"
    SWOT = "swot"
    PYRAMID = "pyramid"
    TIMELINE = "timeline"
    FUNNEL = "funnel"
    QUOTE = "quote"
    CYCLE = "cycle"
    THANKS = "thanks"

    @classmethod
    def get_all_values(cls) -> List[str]:
        """Get all layout values as a list"""
        return [layout.value for layout in cls]

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Check if a value is a valid layout"""
        return value in cls.get_all_values()


LAYOUT_ITEM_AMOUNT_CONSTRAINTS: Dict[Layout, Union[int, tuple[int, int]]] = {
    Layout.ITEMS: (1, 5),
    Layout.STEPS: (3, 5),
    Layout.SUMMARY: (1, 5),
    Layout.COMPARISON: 2,
    Layout.BIG_NUMBER: (1, 5),
    Layout.MILESTONE: (3, 5),
    Layout.PESTEL: 6,
    Layout.SWOT: 4,
    Layout.PYRAMID: (1, 5),
    Layout.TIMELINE: (3, 5),
    Layout.FUNNEL: (3, 5),
    Layout.QUOTE: 1,
    Layout.CYCLE: (3, 5),
    Layout.THANKS: 0,
}


class PresentationRequest(BaseModel):
    length: int
    template: Template
    plain_text: Optional[str] = None
    document_uuids: Optional[List[str]] = None
    language: Optional[str] = None
    fetch_images: Optional[bool] = None
    tone: Tone = Tone.DEFAULT
    verbosity: Verbosity = Verbosity.STANDARD
    custom_user_instructions: Optional[str] = None
    include_cover: Optional[bool] = None
    include_table_of_contents: Optional[bool] = None
    use_branding_logo: Optional[bool] = None
    use_branding_color: Optional[bool] = None
    response_format: ResponseFormat = ResponseFormat.POWERPOINT


class SlideDefinition(BaseModel):
    title: str
    layout: Layout
    item_amount: int
    content: str
    images: Optional[List[str]] = None


class SlideBySlideRequest(BaseModel):
    """Request model for generating a presentation slide by slide"""

    slides: List[SlideDefinition]
    template: Template
    language: Optional[str] = None
    fetch_images: Optional[bool] = None
    include_cover: Optional[bool] = None
    include_table_of_contents: Optional[bool] = None

    @field_validator("slides")
    def validate_slides_item_amount(cls, slides):
        for i, slide in enumerate(slides):
            is_valid, error_message = validate_layout_item_amount(
                slide.layout, slide.item_amount
            )
            if not is_valid:
                raise ValueError(f"Error in slide {i + 1}: {error_message}")
        return slides


class UploadRequest(BaseModel):
    file: Any


class TemplateImages(BaseModel):
    """Image URLs for a presentation template"""

    cover: str
    content: str


class PresentationTemplate(BaseModel):
    """A presentation template with its name and preview images"""

    name: str
    images: TemplateImages


def validate_layout_item_amount(layout: Layout, item_amount: int) -> tuple[bool, str]:
    """
    Validate the item_amount for a given layout.

    Args:
        layout: The layout enum value
        item_amount: The number of items

    Returns:
        A tuple of (is_valid, error_message). If valid, error_message will be empty.
    """
    constraint = LAYOUT_ITEM_AMOUNT_CONSTRAINTS.get(layout)

    if constraint is None:
        return True, ""

    if isinstance(constraint, int):
        if item_amount != constraint:
            return (
                False,
                f"item_amount must be exactly {constraint} for layout '{layout.value}'",
            )
    elif isinstance(constraint, tuple):
        min_allowed, max_allowed = constraint
        if not (min_allowed <= item_amount <= max_allowed):
            return (
                False,
                f"item_amount for layout '{layout.value}' must be between {min_allowed} and {max_allowed}",
            )

    return True, ""
