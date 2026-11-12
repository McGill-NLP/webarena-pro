from __future__ import annotations

from typing import Any


SITE_CONTENT = {
    "name": "TravelMap",
    "tagline": "Easy stays, well chosen.",
    "hero_eyebrow": "Homes for city breaks, design weekends, and longer exhale trips",
    "hero_title": "Find the kind of place that changes the trip.",
    "hero_copy": (
        "Browse beautifully hosted homes with thoughtful details, calm work setups, and neighborhoods "
        "worth walking slowly. From bright lofts to secluded retreats, every stay is set up to feel easy."
    ),
    "footer_headline": "Travel feels better when the place fits the rhythm of the trip.",
    "footer_copy": (
        "Book design-forward homes, save ideas for later, and stay in touch with hosts before you arrive."
    ),
}


CARD_PREVIEWS = {
    "annex-glass-loft": {"label": "Guest favourite", "date_range": "Apr 14-17", "nights": 3},
    "leslieville-garden-suite": {"label": "Guest favourite", "date_range": "Apr 17-19", "nights": 2},
    "joshua-tree-artist-dome": {"label": "Popular this week", "date_range": "May 7-10", "nights": 3},
    "vancouver-seawall-studio": {"label": "Guest favourite", "date_range": "Apr 25-29", "nights": 4},
    "montreal-plateau-book-nook": {"label": "Loved for weekends", "date_range": "May 1-3", "nights": 2},
    "county-barn-retreat": {"label": "Great for groups", "date_range": "Jun 19-22", "nights": 3},
}


CITY_NEARBY = {
    "Toronto": [
        {"name": "Neighborhood cafes", "detail": "Easy morning coffee stops and casual brunch nearby"},
        {"name": "Transit access", "detail": "Quick connections into downtown and surrounding neighborhoods"},
        {"name": "Local restaurants", "detail": "Plenty of walkable dinner options without needing a car"},
    ],
    "Vancouver": [
        {"name": "Waterfront routes", "detail": "Good access to seawall paths, beaches, or harbor walks"},
        {"name": "Transit links", "detail": "Simple buses or bike connections into the rest of the city"},
        {"name": "Neighborhood food", "detail": "Coffee, groceries, and relaxed dinners within a short walk"},
    ],
    "Montreal": [
        {"name": "Cafe culture", "detail": "Strong morning coffee and bakery options close by"},
        {"name": "Walkable streets", "detail": "Best explored slowly, with easy park or shopping stops nearby"},
        {"name": "Evening dining", "detail": "Great casual restaurants and wine bars in the area"},
    ],
    "Prince Edward County": [
        {"name": "County wineries", "detail": "Short drives to vineyards, tasting rooms, and local produce"},
        {"name": "Quiet roads", "detail": "A calm home base for slow weekends and scenic drives"},
        {"name": "Small-town stops", "detail": "Markets, bakeries, and beach access are within easy reach"},
    ],
    "Joshua Tree": [
        {"name": "Park access", "detail": "Trailheads and desert lookouts are within a manageable drive"},
        {"name": "Dark skies", "detail": "The area is well suited to sunset evenings and stargazing"},
        {"name": "Local essentials", "detail": "Town basics, coffee, and supplies are close enough for simple planning"},
    ],
}


LISTING_CONTENT = {
    "annex-glass-loft": {
        "property_type": "Entire loft in Toronto, Canada",
        "tagline": "A plant-filled loft with skylights, warm oak, and an easy Annex rhythm.",
        "overview": [
            "This loft opens up slowly as the day does: first the skylights, then the kitchen, then the row of windows facing a quiet side street in the Annex. It is set up for guests who want a city stay that feels airy, calm, and a little more intentional than a standard apartment rental.",
            "Maya designed the space with long mornings in mind. There is a proper table for lingering breakfasts, a desk that works for full remote-work days, and a kitchen stocked well enough to actually cook dinner before heading out for wine bars, bookstores, or a late film screening."
        ],
        "highlights": [
            "Skylit living area with full-height windows",
            "Chef-ready kitchen with induction range and espresso tools",
            "Dedicated workspace with ergonomic chair and monitor",
            "Fast walk to both Bloor Street and the subway"
        ],
        "sleeping_arrangements": [
            {"name": "Primary bedroom", "details": "Queen bed, blackout drapes, reading sconces"},
            {"name": "Second bedroom", "details": "Double bed, wardrobe, leafy courtyard view"},
            {"name": "Living area", "details": "Deep sofa and record corner for slow evenings"}
        ],
        "guest_favorites": [
            "Morning light in the living room",
            "Cafes and bookstores within a few blocks",
            "Smooth self check-in for late arrivals"
        ],
        "location_blurb": "Set on a quieter Annex street, the loft is close enough to the core to feel connected but tucked away enough to stay calm after dark.",
        "location_highlights": [
            "4-minute walk to Spadina subway access",
            "Excellent coffee, bakeries, and bookstores nearby",
            "Easy transit connection to downtown museums and events"
        ],
        "nearby_spots": [
            {"name": "Bloor Street", "detail": "4-minute walk for neighborhood restaurants, cinemas, and transit"},
            {"name": "Kensington Market", "detail": "18 minutes on foot for vintage shops and casual food stops"},
            {"name": "University of Toronto", "detail": "12-minute walk through one of the prettiest campus areas in the city"}
        ],
        "logistics": [
            "Self check-in with keypad after 4 PM",
            "Quiet hours begin at 10 PM",
            "In-unit washer and detergent provided for longer stays"
        ],
        "host_languages": ["English", "Hindi"],
        "check_in_window": "4:00 PM - 10:00 PM",
        "cancellation_policy": "Free cancellation for 48 hours. Partial refund up to 5 days before arrival.",
        "gallery_images": [
            {"url": "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=1400&q=80", "alt_text": "Sunlit loft living room"},
            {"url": "https://images.unsplash.com/photo-1484154218962-a197022b5858?auto=format&fit=crop&w=1400&q=80", "alt_text": "Warm modern kitchen"},
            {"url": "https://images.unsplash.com/photo-1505693431207-565af06f8d4b?auto=format&fit=crop&w=1400&q=80", "alt_text": "Loft dining table by large windows"},
            {"url": "https://images.unsplash.com/photo-1505692952047-1a78307da8f2?auto=format&fit=crop&w=1400&q=80", "alt_text": "Minimal bedroom with soft light"},
            {"url": "https://images.unsplash.com/photo-1449844908441-8829872d2607?auto=format&fit=crop&w=1400&q=80", "alt_text": "Cozy evening seating corner"}
        ]
    },
    "leslieville-garden-suite": {
        "property_type": "Entire guest suite in Toronto, Canada",
        "tagline": "A quiet lane-house stay with a leafy deck and easy east-end mornings.",
        "overview": [
            "Tucked behind a brick home in Leslieville, this suite has the private, hidden-away feeling people usually want after a full day in the city. It is compact but beautifully thought through, with soft natural textures, a proper coffee setup, and a deck that feels surprisingly secluded.",
            "It suits solo travelers and couples especially well. You can settle in for a few nights without overplanning, then step out to streetcar lines, brunch spots, vintage stores, and the kind of neighborhood restaurants that make the east end such a reliable weekend pick."
        ],
        "highlights": [
            "Private deck with herb planters and evening sun",
            "Lane-house privacy with keypad entry",
            "Well-stocked coffee bar and compact kitchen",
            "Easy streetcar access toward downtown"
        ],
        "sleeping_arrangements": [
            {"name": "Bedroom", "details": "Queen bed, linen headboard, quiet garden-facing window"},
            {"name": "Living nook", "details": "Reading chair, side table, and compact lounge seating"}
        ],
        "guest_favorites": [
            "The deck for coffee or a late glass of wine",
            "A quiet sleep despite being in the city",
            "Easy transit into downtown without needing a car"
        ],
        "location_blurb": "Leslieville has the easy confidence of a neighborhood people actually live in, with independent food spots, parks, and enough transit to keep the rest of the city close.",
        "location_highlights": [
            "Streetcar stop 3 minutes away",
            "Walkable strip of cafes, wine bars, and shops",
            "Short ride to the Distillery District and waterfront"
        ],
        "nearby_spots": [
            {"name": "Queen Street East", "detail": "5-minute walk for coffee bars, brunch, and local shops"},
            {"name": "Jimmie Simpson Park", "detail": "10-minute walk for green space and tennis courts"},
            {"name": "Distillery District", "detail": "15 minutes by transit for galleries and evening drinks"}
        ],
        "logistics": [
            "Keypad self check-in",
            "Street parking is usually available on nearby blocks",
            "Best suited to two guests and light packers"
        ],
        "host_languages": ["English", "Gujarati"],
        "check_in_window": "3:00 PM - 11:00 PM",
        "cancellation_policy": "Free cancellation for 24 hours. Partial refund up to 7 days before arrival.",
        "gallery_images": [
            {"url": "https://images.unsplash.com/photo-1494526585095-c41746248156?auto=format&fit=crop&w=1400&q=80", "alt_text": "Cozy suite living room"},
            {"url": "https://images.unsplash.com/photo-1464890100898-a385f744067f?auto=format&fit=crop&w=1400&q=80", "alt_text": "Light-filled bedroom corner"},
            {"url": "https://images.unsplash.com/photo-1484154218962-a197022b5858?auto=format&fit=crop&w=1400&q=80", "alt_text": "Kitchen and dining nook"},
            {"url": "https://images.unsplash.com/photo-1448630360428-65456885c650?auto=format&fit=crop&w=1400&q=80", "alt_text": "Textured seating area"},
            {"url": "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=1400&q=80", "alt_text": "Open-plan suite with warm finishes"}
        ]
    },
    "joshua-tree-artist-dome": {
        "property_type": "Entire dome in Joshua Tree, United States",
        "tagline": "A cinematic desert stay built for stargazing, records, and complete quiet.",
        "overview": [
            "The dome sits slightly above the valley floor, where the sunset lingers and the dark comes in fast. Jordan shaped the place for a very particular kind of trip: slower mornings, long afternoons outside, and evenings that revolve around music, a fire pit, and the sky doing most of the work.",
            "Inside, the palette stays restrained so the landscape remains the main event. There is enough comfort to stay in all day, but the deck, hot tub, and outdoor shower are the real reason most guests remember this stay long after the trip is over."
        ],
        "highlights": [
            "Dark-sky views from the deck and hot tub",
            "Record player with a rotating vinyl shelf",
            "Outdoor shower and fire pit lounge",
            "Secluded setting with strong design details"
        ],
        "sleeping_arrangements": [
            {"name": "Sleeping loft", "details": "Queen bed under the dome curve with sunrise views"},
            {"name": "Main level", "details": "Lounge seating, reading lamp, and low record shelf"}
        ],
        "guest_favorites": [
            "The stars from the hot tub after dark",
            "How quiet the property feels",
            "A memorable indoor-outdoor flow"
        ],
        "location_blurb": "Panorama Heights gives you a quiet, elevated desert setting while keeping the park entrance and town essentials within a manageable drive.",
        "location_highlights": [
            "10-minute drive to Joshua Tree town center",
            "Quick access to trailheads and park entry",
            "Minimal ambient light for better stargazing"
        ],
        "nearby_spots": [
            {"name": "Joshua Tree National Park", "detail": "15-minute drive for trailheads, climbing, and sunrise loops"},
            {"name": "Pappy + Harriet's", "detail": "30-minute drive for live music and late dinner"},
            {"name": "Noah Purifoy Outdoor Museum", "detail": "20-minute drive for sculpture and open-sky wandering"}
        ],
        "logistics": [
            "Cell service can be spotty on the property",
            "A car is strongly recommended",
            "Outdoor spaces are best enjoyed before peak afternoon heat"
        ],
        "host_languages": ["English", "Spanish"],
        "check_in_window": "4:00 PM - 9:00 PM",
        "cancellation_policy": "Free cancellation for 48 hours. Partial refund up to 14 days before arrival.",
        "gallery_images": [
            {"url": "https://images.unsplash.com/photo-1505692952047-1a78307da8f2?auto=format&fit=crop&w=1400&q=80", "alt_text": "Desert dome exterior at golden hour"},
            {"url": "https://images.unsplash.com/photo-1448630360428-65456885c650?auto=format&fit=crop&w=1400&q=80", "alt_text": "Minimal desert interior"},
            {"url": "https://images.unsplash.com/photo-1502005229762-cf1b2da7c5d6?auto=format&fit=crop&w=1400&q=80", "alt_text": "Warm lounge seating with desert palette"},
            {"url": "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=1400&q=80", "alt_text": "Relaxed bedroom setup with soft textures"},
            {"url": "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?auto=format&fit=crop&w=1400&q=80", "alt_text": "Outdoor deck and evening atmosphere"}
        ]
    },
    "vancouver-seawall-studio": {
        "property_type": "Entire studio in Vancouver, Canada",
        "tagline": "A polished Kits studio for seawall rides, clean mornings, and easy light travel.",
        "overview": [
            "This studio keeps things simple in the right way. The layout is compact, but everything has a place, from the bike storage near the entrance to the quiet desk setup tucked beside the window. It works especially well for travelers who want the city close and their space uncluttered.",
            "Priya hosts it like a basecamp for the neighborhood: reliable shower pressure, calm lighting, laundry on hand, and just enough kitchen setup for breakfast before heading toward the beach, the seawall, or a full workday."
        ],
        "highlights": [
            "Two blocks from the seawall",
            "Private bike storage and gear-friendly entry",
            "Rainfall shower and oak flooring",
            "Calm workspace with natural morning light"
        ],
        "sleeping_arrangements": [
            {"name": "Studio sleeping area", "details": "Queen bed, layered linen, integrated storage wall"},
            {"name": "Living corner", "details": "Compact sofa and table for coffee or remote work"}
        ],
        "guest_favorites": [
            "Easy bike access to the seawall",
            "A clean, quiet place to come home to",
            "Great balance between neighborhood feel and convenience"
        ],
        "location_blurb": "Kitsilano is ideal when you want the water nearby but still want cafes, transit, and dinner options within a few blocks.",
        "location_highlights": [
            "Short walk to the seawall and Kits Beach",
            "Reliable bus access into downtown",
            "Excellent for runners, cyclists, and longer weekend stays"
        ],
        "nearby_spots": [
            {"name": "Kits Beach", "detail": "8-minute walk for sunset swims and beach paths"},
            {"name": "West 4th Avenue", "detail": "6-minute walk for coffee, groceries, and casual shopping"},
            {"name": "Granville Island", "detail": "15 minutes by bike for markets and food stalls"}
        ],
        "logistics": [
            "Ideal for one or two guests traveling light",
            "Bike storage sits just off the main entrance",
            "Laundry supplies and basic toiletries are stocked"
        ],
        "host_languages": ["English", "Malayalam"],
        "check_in_window": "4:00 PM - 10:00 PM",
        "cancellation_policy": "Free cancellation for 48 hours. Partial refund up to 5 days before arrival.",
        "gallery_images": [
            {"url": "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688?auto=format&fit=crop&w=1400&q=80", "alt_text": "Bright studio interior"},
            {"url": "https://images.unsplash.com/photo-1464890100898-a385f744067f?auto=format&fit=crop&w=1400&q=80", "alt_text": "Bedroom corner with window light"},
            {"url": "https://images.unsplash.com/photo-1484154218962-a197022b5858?auto=format&fit=crop&w=1400&q=80", "alt_text": "Compact kitchen with oak details"},
            {"url": "https://images.unsplash.com/photo-1494526585095-c41746248156?auto=format&fit=crop&w=1400&q=80", "alt_text": "Studio lounge seating"},
            {"url": "https://images.unsplash.com/photo-1505693431207-565af06f8d4b?auto=format&fit=crop&w=1400&q=80", "alt_text": "Desk nook in soft daylight"}
        ]
    },
    "montreal-plateau-book-nook": {
        "property_type": "Entire home in Montreal, Canada",
        "tagline": "A bookshelf-lined Plateau stay built for coffee runs, bagels, and slow mornings.",
        "overview": [
            "This apartment has the lived-in warmth that makes a neighborhood stay memorable. Books line the walls, the breakfast table catches good morning light, and the balcony gives you just enough outdoor space to make the place feel expansive.",
            "It is best for guests who want the Plateau at their own pace: bakery in the morning, park walk in the afternoon, maybe records or wine bars later on. The apartment is relaxed and unfussy, but still has all the basics set up properly."
        ],
        "highlights": [
            "Floor-to-ceiling bookshelves and reading corners",
            "Balcony for coffee and people-watching",
            "Walkable access to cafes, parks, and shops",
            "Warm kitchen for simple, longer-stay cooking"
        ],
        "sleeping_arrangements": [
            {"name": "Bedroom", "details": "Queen bed, linen curtains, open bookshelf wall"},
            {"name": "Living room", "details": "Large sofa and reading lamp by the balcony doors"}
        ],
        "guest_favorites": [
            "The apartment feels personal without being cluttered",
            "Excellent morning coffee options nearby",
            "A great home base for walking the neighborhood"
        ],
        "location_blurb": "The Plateau rewards walking, and this apartment places you near parks, casual dining, and some of the city’s best low-key everyday spots.",
        "location_highlights": [
            "Quick walks to cafes and bagel shops",
            "Great park access for slower mornings",
            "One of the city's most enjoyable neighborhoods to explore on foot"
        ],
        "nearby_spots": [
            {"name": "Parc La Fontaine", "detail": "12-minute walk for green space, running paths, and picnics"},
            {"name": "Saint-Laurent Boulevard", "detail": "10-minute walk for bars, record shops, and dining"},
            {"name": "Bagel shops", "detail": "A short stroll for classic Montreal breakfast runs"}
        ],
        "logistics": [
            "The apartment is up one flight of stairs",
            "Best for guests comfortable with a lived-in neighborhood feel",
            "Pets can be considered with advance approval"
        ],
        "host_languages": ["English", "Spanish", "French"],
        "check_in_window": "3:00 PM - 9:00 PM",
        "cancellation_policy": "Free cancellation for 24 hours. Partial refund up to 7 days before arrival.",
        "gallery_images": [
            {"url": "https://images.unsplash.com/photo-1493809842364-78817add7ffb?auto=format&fit=crop&w=1400&q=80", "alt_text": "Book-filled apartment interior"},
            {"url": "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=1400&q=80", "alt_text": "Reading nook with warm light"},
            {"url": "https://images.unsplash.com/photo-1505693431207-565af06f8d4b?auto=format&fit=crop&w=1400&q=80", "alt_text": "Dining table by the window"},
            {"url": "https://images.unsplash.com/photo-1449844908441-8829872d2607?auto=format&fit=crop&w=1400&q=80", "alt_text": "Soft living room textures"},
            {"url": "https://images.unsplash.com/photo-1484154218962-a197022b5858?auto=format&fit=crop&w=1400&q=80", "alt_text": "Kitchen with warm wood finishes"}
        ]
    },
    "county-barn-retreat": {
        "property_type": "Entire barn home in Prince Edward County, Canada",
        "tagline": "A vaulted barn retreat for long-table dinners, wine weekends, and group resets.",
        "overview": [
            "This restored barn is the sort of place that naturally pulls everyone into the same room. The ceilings open high above the main living area, the dining table anchors the house, and the sauna plus vineyard-facing outdoor areas make it easy to stay in without feeling confined.",
            "It works especially well for friends' weekends or family escapes where people want shared space that still feels elevated. The bedrooms are straightforward and comfortable, while the common areas are where the home really earns its keep."
        ],
        "highlights": [
            "Vaulted beam ceilings and oversized communal table",
            "Cedar sauna and vineyard-facing outdoor space",
            "Well-equipped kitchen for group meals",
            "Short drives to wineries and county restaurants"
        ],
        "sleeping_arrangements": [
            {"name": "Primary bedroom", "details": "King bed, ensuite bath, views over the fields"},
            {"name": "Second bedroom", "details": "Queen bed, dresser, warm neutral palette"},
            {"name": "Bunk room", "details": "Two built-in bunks ideal for friends or kids"}
        ],
        "guest_favorites": [
            "Dinner at the long table after winery visits",
            "The sauna on colder evenings",
            "Room for groups without losing the cozy feeling"
        ],
        "location_blurb": "Hillier is a strong base for county weekends, especially if the plan includes wineries, cycling, and returning somewhere quiet after a full day out.",
        "location_highlights": [
            "Close to County wineries and tasting rooms",
            "Easy drives to beaches and small-town stops",
            "Ideal for groups wanting a more private home base"
        ],
        "nearby_spots": [
            {"name": "Hillier wineries", "detail": "Short drive to tasting rooms and vineyard lunches"},
            {"name": "Wellington", "detail": "15 minutes by car for restaurants, groceries, and the water"},
            {"name": "Sandbanks", "detail": "30-minute drive for beach afternoons in warmer weather"}
        ],
        "logistics": [
            "A car is recommended for the County",
            "The house is best enjoyed by groups who plan to cook at least one meal in",
            "Parking for multiple cars is available on site"
        ],
        "host_languages": ["English"],
        "check_in_window": "4:00 PM - 8:00 PM",
        "cancellation_policy": "Free cancellation for 48 hours. Partial refund up to 14 days before arrival.",
        "gallery_images": [
            {"url": "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?auto=format&fit=crop&w=1400&q=80", "alt_text": "Restored barn exterior"},
            {"url": "https://images.unsplash.com/photo-1502005229762-cf1b2da7c5d6?auto=format&fit=crop&w=1400&q=80", "alt_text": "Barn living area with beams"},
            {"url": "https://images.unsplash.com/photo-1505693416388-ac5ce068fe85?auto=format&fit=crop&w=1400&q=80", "alt_text": "Large communal dining space"},
            {"url": "https://images.unsplash.com/photo-1484154218962-a197022b5858?auto=format&fit=crop&w=1400&q=80", "alt_text": "Kitchen for group cooking"},
            {"url": "https://images.unsplash.com/photo-1449844908441-8829872d2607?auto=format&fit=crop&w=1400&q=80", "alt_text": "Cozy evening seating inside the barn"}
        ]
    }
}


def _pluralize(value: int, singular: str, plural: str | None = None) -> str:
    if value == 1:
        return singular
    return plural or f"{singular}s"


def _default_sleeping_arrangements(listing: Any) -> list[dict[str, str]]:
    arrangements = []
    for index in range(max(listing.bedrooms, 1)):
        if index == 0:
            name = "Primary bedroom"
        elif index == 1:
            name = "Second bedroom"
        else:
            name = f"Bedroom {index + 1}"
        details = (
            f"{'Queen' if listing.beds <= 2 else 'Double'} bed, soft lighting, and storage for longer stays"
        )
        arrangements.append({"name": name, "details": details})
    if listing.bedrooms == 1:
        arrangements.append({"name": "Living area", "details": "Comfortable seating for reading, coffee, or a slower evening in"})
    return arrangements


def _default_nearby_spots(listing: Any) -> list[dict[str, str]]:
    if listing.city in CITY_NEARBY:
        return CITY_NEARBY[listing.city]
    return [
        {"name": f"{listing.neighborhood} streets", "detail": "A good base for easy walks, coffee stops, and getting oriented quickly"},
        {"name": f"{listing.city} essentials", "detail": "Groceries, casual dining, and transit or parking access nearby"},
        {"name": "Local highlights", "detail": "A relaxed area to settle into without overplanning the stay"},
    ]


def _build_default_listing_content(listing: Any) -> dict[str, Any]:
    amenity_highlights = listing.amenities[:4]
    beds_label = _pluralize(listing.beds, "bed")
    bedrooms_label = _pluralize(listing.bedrooms, "bedroom")
    property_type = f"Entire home in {listing.city}, {listing.country}"
    return {
        "property_type": property_type,
        "tagline": f"A welcoming stay in {listing.neighborhood} with room to settle in and stay awhile.",
        "overview": [
            listing.description,
            f"The home is arranged for up to {listing.max_guests} guests, with {listing.bedrooms} {bedrooms_label}, {listing.beds} {beds_label}, and the everyday comforts that make short trips feel easy from the first night.",
        ],
        "highlights": amenity_highlights or ["Comfortable interiors", "Well-located stay", "Smooth arrival setup", "Thoughtful host touches"],
        "sleeping_arrangements": _default_sleeping_arrangements(listing),
        "guest_favorites": amenity_highlights[:3] or ["Great location", "Comfortable layout", "Easy arrival"],
        "location_blurb": f"{listing.neighborhood} is a strong base in {listing.city} when you want a stay that feels connected to the neighborhood without being hard to settle into.",
        "location_highlights": [
            f"Easy access to {listing.neighborhood}",
            f"Good base for exploring {listing.city}",
            "Plenty of everyday essentials close by",
        ],
        "nearby_spots": _default_nearby_spots(listing),
        "logistics": [
            "Self check-in details are shared before arrival",
            f"Best suited to up to {listing.max_guests} guests",
            f"Cleaning fee of ${listing.cleaning_fee:,.0f} and service fee of ${listing.service_fee:,.0f} are applied separately",
        ],
        "host_languages": ["English"],
        "check_in_window": "4:00 PM - 10:00 PM",
        "cancellation_policy": "Free cancellation within 48 hours. Partial refund available closer to arrival.",
        "gallery_images": [],
    }


def get_listing_content(listing_or_slug: Any) -> dict[str, Any]:
    if hasattr(listing_or_slug, "slug"):
        listing = listing_or_slug
        slug = listing.slug
    else:
        listing = None
        slug = str(listing_or_slug)

    base_content = _build_default_listing_content(listing) if listing is not None else {
        "property_type": "Entire home",
        "tagline": "A comfortable stay in a great neighborhood.",
        "overview": [],
        "highlights": [],
        "sleeping_arrangements": [],
        "guest_favorites": [],
        "location_blurb": "",
        "location_highlights": [],
        "nearby_spots": [],
        "logistics": [],
        "host_languages": ["English"],
        "check_in_window": "4:00 PM - 10:00 PM",
        "cancellation_policy": "Free cancellation within 48 hours.",
        "gallery_images": [],
    }
    return {
        **base_content,
        **LISTING_CONTENT.get(slug, {}),
    }


def get_listing_property_category(listing: Any) -> str:
    """Return the structured marketplace category shown in search filters."""
    property_type = get_listing_content(listing)["property_type"].lower()
    category_markers = (
        ("guest suite", "Guest suite"),
        ("loft", "Loft"),
        ("studio", "Studio"),
        ("apartment", "Apartment"),
        ("house", "House"),
        ("dome", "Dome"),
        ("barn", "Barn"),
    )
    for marker, category in category_markers:
        if marker in property_type:
            return category
    return "House"


def get_listing_card_meta(listing: Any) -> dict[str, Any]:
    if listing.slug in CARD_PREVIEWS:
        preview = CARD_PREVIEWS[listing.slug]
    else:
        generated_labels = ["Guest favourite", "Popular this week", "Loved for weekends", "Top-rated stay"]
        generated_dates = [
            ("Apr 3-5", 2),
            ("Apr 10-13", 3),
            ("Apr 17-20", 3),
            ("Apr 24-26", 2),
            ("May 1-4", 3),
            ("May 8-10", 2),
            ("May 15-18", 3),
            ("Jun 5-8", 3),
        ]
        date_range, nights = generated_dates[listing.id % len(generated_dates)]
        preview = {
            "label": generated_labels[listing.id % len(generated_labels)],
            "date_range": date_range,
            "nights": nights,
        }
    nights = max(int(preview["nights"]), 1)
    total_price = listing.price_per_night * nights + listing.cleaning_fee + listing.service_fee
    return {
        "label": preview["label"],
        "date_range": preview["date_range"],
        "total_price_display": f"${total_price:,.0f} total",
        "rating_display": f"{listing.rating:.2f}",
    }
