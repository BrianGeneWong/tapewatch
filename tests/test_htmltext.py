from tapewatch.htmltext import html_to_text


def test_soft_wraps_inside_text_are_collapsed():
    # Filing HTML wraps mid-phrase; the name must survive intact.
    assert html_to_text("<p>Victory\nCapital Holdings, Inc.</p>") == (
        "Victory Capital Holdings, Inc."
    )


def test_block_tags_still_break_lines():
    assert html_to_text("<p>One</p><p>Two</p>") == "One\nTwo"


def test_ixbrl_header_is_dropped():
    html = (
        "<ix:header><ix:hidden>iso4217:USD xbrli:shares</ix:hidden></ix:header>"
        "<p>FORM 8-K</p>"
    )
    assert html_to_text(html) == "FORM 8-K"


def test_scripts_and_styles_dropped():
    assert html_to_text("<style>p{color:red}</style><p>Body</p>") == "Body"


def test_nbsp_normalized():
    assert html_to_text("<p>A&nbsp;B</p>") == "A B"
