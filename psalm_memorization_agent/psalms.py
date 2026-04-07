"""
NKJV Psalm texts and chunk definitions.
Psalms are hardcoded to avoid any external API dependency.
"""

# Each psalm entry: id (1-8), title, verses (list of strings), chunks (list of verse ranges)
# chunk_number 0 = full psalm; chunk_number 1..N = individual chunks

PSALM_DATA = {
    1: {
        "title": "Psalm 1",
        "verses": [
            "Blessed is the man who walks not in the counsel of the ungodly, nor stands in the path of sinners, nor sits in the seat of the scornful;",
            "But his delight is in the law of the Lord, and in His law he meditates day and night.",
            "He shall be like a tree planted by the rivers of water, that brings forth its fruit in its season, whose leaf also shall not wither; and whatever he does shall prosper.",
            "The ungodly are not so, but are like the chaff which the wind drives away.",
            "Therefore the ungodly shall not stand in the judgment, nor sinners in the congregation of the righteous.",
            "For the Lord knows the way of the righteous, but the way of the ungodly shall perish.",
        ],
        "chunks": [
            (1, 2),  # chunk 1: v1-2
            (3, 4),  # chunk 2: v3-4
            (5, 6),  # chunk 3: v5-6
        ],
    },
    2: {
        "title": "Psalm 23",
        "verses": [
            "The Lord is my shepherd; I shall not want.",
            "He makes me to lie down in green pastures; He leads me beside the still waters.",
            "He restores my soul; He leads me in the paths of righteousness for His name's sake.",
            "Yea, though I walk through the valley of the shadow of death, I will fear no evil; for You are with me; Your rod and Your staff, they comfort me.",
            "You prepare a table before me in the presence of my enemies; You anoint my head with oil; my cup runs over.",
            "Surely goodness and mercy shall follow me all the days of my life; and I will dwell in the house of the Lord forever.",
        ],
        "chunks": [
            (1, 3),  # chunk 1: v1-3
            (4, 6),  # chunk 2: v4-6
        ],
    },
    3: {
        "title": "Psalm 27:1",
        "verses": [
            "The Lord is my light and my salvation; whom shall I fear? The Lord is the strength of my life; of whom shall I be afraid?",
        ],
        "chunks": [],  # no sub-chunks; drill modes apply directly to the single verse
    },
    4: {
        "title": "Psalm 46",
        "verses": [
            "God is our refuge and strength, a very present help in trouble.",
            "Therefore we will not fear, even though the earth be removed, and though the mountains be carried into the midst of the sea;",
            "Though its waters roar and be troubled, though the mountains shake with its swelling. Selah",
            "There is a river whose streams shall make glad the city of God, the holy place of the tabernacle of the Most High.",
            "God is in the midst of her, she shall not be moved; God shall help her, just at the break of dawn.",
            "The nations raged, the kingdoms were moved; He uttered His voice, the earth melted.",
            "The Lord of hosts is with us; the God of Jacob is our refuge. Selah",
            "Come, behold the works of the Lord, who has made desolations in the earth.",
            "He makes wars cease to the end of the earth; He breaks the bow and cuts the spear in two; He burns the chariot in the fire.",
            "Be still, and know that I am God; I will be exalted among the nations, I will be exalted in the earth!",
            "The Lord of hosts is with us; the God of Jacob is our refuge. Selah",
        ],
        "chunks": [
            (1, 3),   # chunk 1: v1-3
            (4, 7),   # chunk 2: v4-7
            (8, 11),  # chunk 3: v8-11
        ],
    },
    5: {
        "title": "Psalm 91",
        "verses": [
            "He who dwells in the secret place of the Most High shall abide under the shadow of the Almighty.",
            "I will say of the Lord, \"He is my refuge and my fortress; my God, in Him I will trust.\"",
            "Surely He shall deliver you from the snare of the fowler and from the perilous pestilence.",
            "He shall cover you with His feathers, and under His wings you shall take refuge; His truth shall be your shield and buckler.",
            "You shall not be afraid of the terror by night, nor of the arrow that flies by day,",
            "Nor of the pestilence that walks in darkness, nor of the destruction that lays waste at noonday.",
            "A thousand may fall at your side, and ten thousand at your right hand; but it shall not come near you.",
            "Only with your eyes shall you look, and see the reward of the wicked.",
            "Because you have made the Lord, who is my refuge, even the Most High, your dwelling place,",
            "No evil shall befall you, nor shall any plague come near your dwelling;",
            "For He shall give His angels charge over you, to keep you in all your ways.",
            "In their hands they shall bear you up, lest you dash your foot against a stone.",
            "You shall tread upon the lion and the cobra, the young lion and the serpent you shall trample underfoot.",
            "\"Because he has set his love upon Me, therefore I will deliver him; I will set him on high, because he has known My name.\"",
            "\"He shall call upon Me, and I will answer him; I will be with him in trouble; I will deliver him and honor him.\"",
            "\"With long life I will satisfy him, and show him My salvation.\"",
        ],
        "chunks": [
            (1, 4),    # chunk 1: v1-4
            (5, 9),    # chunk 2: v5-9
            (10, 13),  # chunk 3: v10-13
            (14, 16),  # chunk 4: v14-16
        ],
    },
    6: {
        "title": "Psalm 100",
        "verses": [
            "Make a joyful shout to the Lord, all you lands!",
            "Serve the Lord with gladness; come before His presence with singing.",
            "Know that the Lord, He is God; it is He who has made us, and not we ourselves; we are His people and the sheep of His pasture.",
            "Enter into His gates with thanksgiving, and into His courts with praise. Be thankful to Him, and bless His name.",
            "For the Lord is good; His mercy is everlasting, and His truth endures to all generations.",
        ],
        "chunks": [
            (1, 3),  # chunk 1: v1-3
            (4, 5),  # chunk 2: v4-5
        ],
    },
    7: {
        "title": "Psalm 119:105",
        "verses": [
            "Your word is a lamp to my feet and a light to my path.",
        ],
        "chunks": [],  # no sub-chunks
    },
    8: {
        "title": "Psalm 121",
        "verses": [
            "I will lift up my eyes to the hills — from whence comes my help?",
            "My help comes from the Lord, who made heaven and earth.",
            "He will not allow your foot to be moved; He who keeps you will not slumber.",
            "Behold, He who keeps Israel shall neither slumber nor sleep.",
            "The Lord is your keeper; the Lord is your shade at your right hand.",
            "The sun shall not strike you by day, nor the moon by night.",
            "The Lord shall preserve you from all evil; He shall preserve your soul.",
            "The Lord shall preserve your going out and your coming in from this time forth, and even forevermore.",
        ],
        "chunks": [
            (1, 4),  # chunk 1: v1-4
            (5, 8),  # chunk 2: v5-8
        ],
    },
}


def get_psalm(psalm_id: int) -> dict:
    return PSALM_DATA[psalm_id]


def get_chunk_text(psalm_id: int, chunk_number: int) -> str:
    """
    Return the text for a given chunk.
    chunk_number 0 = full psalm.
    chunk_number 1..N = specific chunk.
    For psalms with no sub-chunks (3 and 7), chunk_number 1 = full psalm.
    """
    psalm = PSALM_DATA[psalm_id]
    verses = psalm["verses"]
    chunks = psalm["chunks"]

    if chunk_number == 0:
        # Full psalm
        return " ".join(verses)

    if not chunks:
        # Single-verse psalm — treat chunk 1 as the whole thing
        return " ".join(verses)

    start_v, end_v = chunks[chunk_number - 1]  # 1-indexed chunk_number
    selected = verses[start_v - 1 : end_v]
    return " ".join(selected)


def get_total_chunks(psalm_id: int) -> int:
    """Number of sub-chunks. 0 if the psalm has no chunks (single verse)."""
    psalm = PSALM_DATA[psalm_id]
    if not psalm["chunks"]:
        return 0
    return len(psalm["chunks"])


def count_words(text: str) -> int:
    return len(text.split())


# Pre-written built-in messages (no Claude API call needed)

SUCCESS_MESSAGES = [
    "Great job — you nailed it!",
    "Excellent work! Keep it up!",
    "That's the way! Well done.",
    "You're on fire! Awesome attempt.",
    "Nailed it! You're making real progress.",
    "Way to go! That was spot on.",
]

CHUNK_MASTERY_MESSAGES = {
    # psalm_id -> chunk_number -> message
    1: {
        1: "You've mastered the opening of Psalm 1 — 'Blessed is the man who walks not in the counsel of the ungodly.'",
        2: "Chunk 2 of Psalm 1 mastered! The image of a fruitful tree is yours to keep.",
        3: "You've mastered all of Psalm 1's chunks! Time for the full recitation.",
    },
    2: {
        1: "Chunk 1 of Psalm 23 down — 'The Lord is my shepherd' is locked in!",
        2: "The second half of Psalm 23 is yours! Get ready for the full psalm.",
    },
    3: {
        1: "You've mastered Psalm 27:1 — what a powerful verse to carry with you!",
    },
    4: {
        1: "Chunk 1 of Psalm 46 mastered — 'God is our refuge and strength.'",
        2: "Chunk 2 of Psalm 46 done! The river of God flows through your memory.",
        3: "All chunks of Psalm 46 mastered! 'Be still, and know that I am God.'",
    },
    5: {
        1: "Chunk 1 of Psalm 91 mastered — the shadow of the Almighty is yours.",
        2: "Chunk 2 of Psalm 91 done! No terror by night or arrow by day can shake you.",
        3: "Chunk 3 of Psalm 91 mastered — His angels have charge over you!",
        4: "All chunks of Psalm 91 complete! The boss level is in reach.",
    },
    6: {
        1: "Chunk 1 of Psalm 100 mastered — 'Make a joyful shout to the Lord!'",
        2: "Chunk 2 of Psalm 100 done! 'His mercy is everlasting' — and so is your memory!",
    },
    7: {
        1: "Psalm 119:105 mastered — 'Your word is a lamp to my feet.' Light the way!",
    },
    8: {
        1: "Chunk 1 of Psalm 121 mastered — 'My help comes from the Lord.'",
        2: "All chunks of Psalm 121 mastered! Time to put it all together.",
    },
}

PSALM_MASTERY_MESSAGES = {
    1: "You've fully mastered Psalm 1! This psalm paints a picture of someone rooted in God's Word, fruitful and unshaken. Carry it with you.",
    2: "Psalm 23 is yours! The Good Shepherd leads you through every valley. What a treasure to have this psalm by heart.",
    3: "Psalm 27:1 mastered! Whenever fear comes, you can declare: 'The Lord is my light and my salvation — whom shall I fear?'",
    4: "You've conquered Psalm 46! 'Be still, and know that I am God.' You can return to these words whenever the world feels shaky.",
    5: "BOSS LEVEL CLEARED! Psalm 91 is yours — all 16 verses! You carry one of the most powerful promises in Scripture. Incredible work.",
    6: "Psalm 100 mastered! 'Enter into His gates with thanksgiving.' You've hidden a song of praise in your heart.",
    7: "Psalm 119:105 is yours forever — 'Your word is a lamp to my feet and a light to my path.' Short verse, huge truth.",
    8: "Psalm 121 fully mastered! 'The Lord shall preserve your going out and your coming in.' He watches over you always.",
}
