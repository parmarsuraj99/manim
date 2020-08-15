from functools import reduce
import operator as op
import attr
import typing as tp

from colour import Color
from ...constants import *
from ...config import config
from ...mobject.geometry import Line
from ...mobject.svg.svg_mobject import SVGMobject
from ...mobject.svg.svg_mobject import VMobjectFromSVGPathstring
from ...mobject.types.vectorized_mobject import VGroup
from ...mobject.types.vectorized_mobject import VectorizedPoint
from ...utils.config_ops import digest_config
from ...utils.strings import split_string_list_to_isolate_substrings
from ...utils.tex_file_writing import tex_to_svg_file

TEX_MOB_SCALE_FACTOR = 0.05


@attr.s(auto_attribs=True, eq=False)
class TexSymbol(VMobjectFromSVGPathstring):
    """Purely a renaming of VMobjectFromSVGPathstring."""

    def __attrs_post_init__(self):
        VMobjectFromSVGPathstring.__attrs_post_init__(self)


@attr.s(auto_attribs=True, eq=False)
class SingleStringTexMobject(SVGMobject):
    stroke_width: float = 0
    fill_opacity: float = 1.0
    background_stroke_width: float = 1
    background_stroke_color: tp.Union[str, Color] = BLACK
    should_center: bool = True
    height: tp.Union[float] = None
    organize_left_to_right: bool = False
    alignment: str = ""
    type: str = "tex"
    tex_string: tp.Optional[str] = None

    def __attrs_post_init__(self):
        assert isinstance(self.tex_string, str)
        self.file_name = tex_to_svg_file(self.get_modified_expression(self.tex_string), self.type)
        SVGMobject.__attrs_post_init__(self)
        if self.height is None:
            self.scale(TEX_MOB_SCALE_FACTOR)
        if self.organize_left_to_right:
            self.organize_submobjects_left_to_right()

    @classmethod
    def from_other_config(cls, tex_string, **kwargs):
        new_kwargs = {}
        fields = attr.fields_dict(cls)
        for key in kwargs.keys():
            if key in fields:
                new_kwargs[key] = kwargs[key]
        return cls(tex_string=tex_string, **new_kwargs)

    def get_modified_expression(self, tex_string):
        result = self.alignment + " " + tex_string
        result = result.strip()
        result = self.modify_special_strings(result)
        return result

    def modify_special_strings(self, tex):
        tex = self.remove_stray_braces(tex)
        should_add_filler = reduce(
            op.or_,
            [
                # Fraction line needs something to be over
                tex == "\\over",
                tex == "\\overline",
                # Makesure sqrt has overbar
                tex == "\\sqrt",
                # Need to add blank subscript or superscript
                tex.endswith("_"),
                tex.endswith("^"),
                tex.endswith("dot"),
            ],
        )
        if should_add_filler:
            filler = "{\\quad}"
            tex += filler

        if tex == "\\substack":
            tex = "\\quad"

        if tex == "":
            tex = "\\quad"

        # To keep files from starting with a line break
        if tex.startswith("\\\\"):
            tex = tex.replace("\\\\", "\\quad\\\\")

        # Handle imbalanced \left and \right
        num_lefts, num_rights = [
            len([s for s in tex.split(substr)[1:] if s and s[0] in "(){}[]|.\\"])
            for substr in ("\\left", "\\right")
        ]
        if num_lefts != num_rights:
            tex = tex.replace("\\left", "\\big")
            tex = tex.replace("\\right", "\\big")

        for context in ["array"]:
            begin_in = ("\\begin{%s}" % context) in tex
            end_in = ("\\end{%s}" % context) in tex
            if begin_in ^ end_in:
                # Just turn this into a blank string,
                # which means caller should leave a
                # stray \\begin{...} with other symbols
                tex = ""
        return tex

    def remove_stray_braces(self, tex):
        """
        Makes TexMobject resiliant to unmatched { at start
        """
        num_lefts, num_rights = [tex.count(char) for char in "{}"]
        while num_rights > num_lefts:
            tex = "{" + tex
            num_lefts += 1
        while num_lefts > num_rights:
            tex = tex + "}"
            num_rights += 1
        return tex

    def get_tex_string(self):
        return self.tex_string

    def path_string_to_mobject(self, path_string):
        # Overwrite superclass default to use
        # specialized path_string mobject
        return TexSymbol(path_string=path_string)

    def organize_submobjects_left_to_right(self):
        self.sort(lambda p: p[0])
        return self


@attr.s(auto_attribs=True, eq=False)
class TexMobject(SingleStringTexMobject):
    arg_separator: str = " "
    substrings_to_isolate: tp.List = []
    tex_to_color_map: tp.Dict = {}
    tex_strings: tp.List = []

    def __attrs_post_init__(self):
        self.tex_strings = self.break_up_tex_strings(self.tex_strings)
        self.tex_string = self.arg_separator.join(self.tex_strings)
        SingleStringTexMobject.__attrs_post_init__(self)
        self.break_up_by_substrings()
        self.set_color_by_tex_to_color_map(self.tex_to_color_map)

        if self.organize_left_to_right:
            self.organize_submobjects_left_to_right()

    def break_up_tex_strings(self, tex_strings):
        substrings_to_isolate = op.add(
            self.substrings_to_isolate, list(self.tex_to_color_map.keys())
        )
        split_list = split_string_list_to_isolate_substrings(
            tex_strings, *substrings_to_isolate
        )
        if self.arg_separator == " ":
            split_list = [str(x).strip() for x in split_list]
        # split_list = list(map(str.strip, split_list))
        split_list = [s for s in split_list if s != ""]
        return split_list

    def break_up_by_substrings(self):
        """
        Reorganize existing submojects one layer
        deeper based on the structure of tex_strings (as a list
        of tex_strings)
        """
        new_submobjects = []
        curr_index = 0
        # TODO what should actually by passed by this dict ?
        config = {
            "substrings_to_isolate": self.substrings_to_isolate,
            "tex_to_color_map": self.tex_to_color_map,
            "type": self.type,
            "alignment": "",
        }
        for tex_string in self.tex_strings:
            sub_tex_mob = SingleStringTexMobject.from_other_config(tex_string, **config)
            num_submobs = len(sub_tex_mob.submobjects)
            new_index = curr_index + num_submobs
            if num_submobs == 0:
                # For cases like empty tex_strings, we want the corresponing
                # part of the whole TexMobject to be a VectorizedPoint
                # positioned in the right part of the TexMobject
                sub_tex_mob.submobjects = [VectorizedPoint()]
                last_submob_index = min(curr_index, len(self.submobjects) - 1)
                sub_tex_mob.move_to(self.submobjects[last_submob_index], RIGHT)
            else:
                sub_tex_mob.submobjects = self.submobjects[curr_index:new_index]
            new_submobjects.append(sub_tex_mob)
            curr_index = new_index
        self.submobjects = new_submobjects
        return self

    def get_parts_by_tex(self, tex, substring=True, case_sensitive=True):
        def test(tex1, tex2):
            if not case_sensitive:
                tex1 = tex1.lower()
                tex2 = tex2.lower()
            if substring:
                return tex1 in tex2
            else:
                return tex1 == tex2

        return VGroup.from_vmobjects(*[m for m in self.submobjects if test(tex, m.get_tex_string())])

    def get_part_by_tex(self, tex, **kwargs):
        all_parts = self.get_parts_by_tex(tex, **kwargs)
        return all_parts[0] if all_parts else None

    def set_color_by_tex(self, tex, color, **kwargs):
        parts_to_color = self.get_parts_by_tex(tex, **kwargs)
        for part in parts_to_color:
            part.set_color(color)
        return self

    def set_color_by_tex_to_color_map(self, texs_to_color_map, **kwargs):
        for texs, color in list(texs_to_color_map.items()):
            try:
                # If the given key behaves like tex_strings
                texs + ""
                self.set_color_by_tex(texs, color, **kwargs)
            except TypeError:
                # If the given key is a tuple
                for tex in texs:
                    self.set_color_by_tex(tex, color, **kwargs)
        return self

    def index_of_part(self, part):
        split_self = self.split()
        if part not in split_self:
            raise Exception("Trying to get index of part not in TexMobject")
        return split_self.index(part)

    def index_of_part_by_tex(self, tex, **kwargs):
        part = self.get_part_by_tex(tex, **kwargs)
        return self.index_of_part(part)

    def sort_alphabetically(self):
        self.submobjects.sort(key=lambda m: m.get_tex_string())


@attr.s(auto_attribs=True, eq=False)
class TextMobject(TexMobject):
    alignment: str = "\\centering"
    arg_separator: str = ""
    type: str = "text"

    def __attrs_post_init__(self):
        TexMobject.__attrs_post_init__(self)


@attr.s(auto_attribs=True, eq=False)
class BulletedList(TextMobject):
    buff: float = MED_LARGE_BUFF
    dot_scale_factor: float = 2
    # Have to include because of handle_multiple_args implementation
    alignment: str = ""
    items: tp.List = []

    def __attrs_post_init__(self):
        line_separated_items = [s + "\\\\" for s in self.items]
        self.tex_strings = line_separated_items
        TextMobject.__attrs_post_init__(self)
        for part in self:
            dot = TexMobject(tex_strings=["\\cdot"]).scale(self.dot_scale_factor)
            dot.next_to(part[0], LEFT, SMALL_BUFF)
            part.add_to_back(dot)
        self.arrange(DOWN, aligned_edge=LEFT, buff=self.buff)

    def fade_all_but(self, index_or_string, opacity=0.5):
        arg = index_or_string
        if isinstance(arg, str):
            part = self.get_part_by_tex(arg)
        elif isinstance(arg, int):
            part = self.submobjects[arg]
        else:
            raise Exception("Expected int or string, got {0}".format(arg))
        for other_part in self.submobjects:
            if other_part is part:
                other_part.set_fill(opacity=1)
            else:
                other_part.set_fill(opacity=opacity)


@attr.s(auto_attribs=True, eq=False)
class TexMobjectFromPresetString(TexMobject):
    # To be filled by subclasses
    tex: tp.Any = None
    color: tp.Union[str, Color] = None

    def __attrs_post_init__(self):
        TexMobject.__attrs_post_init__(self)
        self.set_color(self.color)


@attr.s(auto_attribs=True, eq=False)
class Title(TextMobject):
    scale_factor: float = 1
    include_underline: bool = True
    underline_width: float = config["frame_width"] - 2
    # This will override underline_width
    match_underline_width_to_text: bool = False
    underline_buff: float = MED_SMALL_BUFF

    def __attrs_post_init__(self):
        TextMobject.__attrs_post_init__(self)
        self.scale(self.scale_factor)
        self.to_edge(UP)
        if self.include_underline:
            underline = Line(start=LEFT, end=RIGHT)
            underline.next_to(self, DOWN, buff=self.underline_buff)
            if self.match_underline_width_to_text:
                underline.match_width(self)
            else:
                underline.set_width(self.underline_width)
            self.add(underline)
            self.underline = underline
