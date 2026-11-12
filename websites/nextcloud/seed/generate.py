#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generate the deterministic, open-licensed Nextcloud seed dataset."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import shutil
import textwrap
import zipfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree


GENERATOR_VERSION = 2
COMPANY_NAME = "Cedarstone Analytics"
COMPANY_DOMAIN = "cedarstone.test"
COMPANY_ADDRESS = "250 Cedarstone Way, Toronto, Ontario"
USERS = ("maya.patel", "daniel.brooks")
SUPPORT_USERS = ("sarah", "priya", "marcus", "leon")
TALK_USERS = USERS + SUPPORT_USERS
DATASET_CREATOR = "WebArena-Pro contributors"
DATASET_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
CC0_LICENSE_URL = "https://creativecommons.org/publicdomain/zero/1.0/"
ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)
RESERVED_BULK_TERMS = {
    "project alpha",
    "project charlie",
    "marketing assistant",
    "freelance invoice payment due",
    "project alpha ui mockups due",
    "leon green",
    "sarah garcia",
}

SHARED_CONTACTS = [
    ("Alex Johnson", "alex.j@cedarstone.test", "555-0101"),
    ("Maria Garcia", "maria.g@cedarstone.test", "555-0102"),
    ("James Smith", "james.s@cedarstone.test", "555-0103"),
    ("Linda Martinez", "linda.m@cedarstone.test", "555-0104"),
    ("Robert Brown", "robert.b@cedarstone.test", "555-0105"),
    ("Patricia Davis", "patricia.d@cedarstone.test", "555-0106"),
    ("Michael Miller", "michael.m@cedarstone.test", "555-0107"),
    ("Jennifer Wilson", "jennifer.w@cedarstone.test", "555-0108"),
    ("William Moore", "william.m@cedarstone.test", "555-0109"),
    ("Elizabeth Taylor", "elizabeth.t@cedarstone.test", "555-0110"),
    ("David Anderson", "david.a@cedarstone.test", "555-0111"),
    ("Barbara Thomas", "barbara.t@cedarstone.test", "555-0112"),
    ("Richard Jackson", "richard.j@cedarstone.test", "555-0113"),
    ("Susan White", "susan.w@cedarstone.test", "555-0114"),
    ("Joseph Harris", "joseph.h@cedarstone.test", "555-0115"),
    ("Jessica Martin", "jessica.m@cedarstone.test", "555-0116"),
    ("Thomas Thompson", "thomas.t@cedarstone.test", "555-0117"),
    ("Sarah Garcia", "sarah.g@cedarstone.test", "555-0118"),
    ("Charles Martinez", "charles.m@cedarstone.test", "555-0119"),
    ("Karen Robinson", "karen.r@cedarstone.test", "555-0120"),
]

AGENT_CONTACTS = {
    "maya.patel": [
        ("Christopher Clark", "chris.c@cedarstone.test", "555-0201"),
        ("Nancy Rodriguez", "nancy.r@cedarstone.test", "555-0202"),
        ("Daniel Lewis", "daniel.l@cedarstone.test", "555-0203"),
        ("Lisa Lee", "lisa.l@cedarstone.test", "555-0204"),
        ("Matthew Walker", "matthew.w@cedarstone.test", "555-0205"),
        ("Betty Hall", "betty.h@cedarstone.test", "555-0206"),
        ("Anthony Allen", "anthony.a@cedarstone.test", "555-0207"),
        ("Margaret Young", "margaret.y@cedarstone.test", "555-0208"),
        ("Mark Hernandez", "mark.h@cedarstone.test", "555-0209"),
        ("Sandra King", "sandra.k@cedarstone.test", "555-0210"),
    ],
    "daniel.brooks": [
        ("Donald Wright", "donald.w@cedarstone.test", "555-0301"),
        ("Ashley Lopez", "ashley.l@cedarstone.test", "555-0302"),
        ("Steven Hill", "steven.h@cedarstone.test", "555-0303"),
        ("Kimberly Scott", "kimberly.s@cedarstone.test", "555-0304"),
        ("Paul Green", "paul.g@cedarstone.test", "555-0305"),
        ("Emily Adams", "emily.a@cedarstone.test", "555-0306"),
        ("Andrew Baker", "andrew.b@cedarstone.test", "555-0307"),
        ("Donna Gonzalez", "donna.g@cedarstone.test", "555-0308"),
        ("Joshua Nelson", "joshua.n@cedarstone.test", "555-0309"),
        ("Carol Carter", "carol.c@cedarstone.test", "555-0310"),
    ],
}

SYNTHETIC_CONTACTS = {
    "maya.patel": [
        ("Leon Greene", "leon@cedarstone.test", "9999999999", "Leon Green"),
        ("Sarah Chen", "sarah.chen@cedarstone.test", "555-0490", ""),
        ("Priya Nair", "priya.nair@cedarstone.test", "555-0491", ""),
        ("Marcus Johnson", "marcus.johnson@cedarstone.test", "555-0492", ""),
        ("Avery Brooks", "avery.brooks@cedarstone.test", "555-0402", ""),
        ("Morgan Reed", "morgan.reed@cedarstone.test", "555-0403", ""),
        ("Jordan Kim", "jordan.kim@cedarstone.test", "555-0404", ""),
        ("Riley Patel", "riley.patel@cedarstone.test", "555-0405", ""),
        ("Cameron Price", "cameron.price@cedarstone.test", "555-0406", ""),
        ("Taylor Nguyen", "taylor.nguyen@cedarstone.test", "555-0407", ""),
        ("Casey Morgan", "casey.morgan@cedarstone.test", "555-0408", ""),
        ("Parker Evans", "parker.evans@cedarstone.test", "555-0409", ""),
        ("Quinn Foster", "quinn.foster@cedarstone.test", "555-0410", ""),
        ("Drew Howard", "drew.howard@cedarstone.test", "555-0411", ""),
        ("Skyler Ward", "skyler.ward@cedarstone.test", "555-0412", ""),
        ("Emerson Bell", "emerson.bell@cedarstone.test", "555-0413", ""),
        ("Rowan Cook", "rowan.cook@cedarstone.test", "555-0414", ""),
        ("Finley Gray", "finley.gray@cedarstone.test", "555-0415", ""),
        ("Reese Perry", "reese.perry@cedarstone.test", "555-0416", ""),
        ("Hayden Bailey", "hayden.bailey@cedarstone.test", "555-0417", ""),
    ],
    "daniel.brooks": [
        ("Leon Greene", "leon@cedarstone.test", "9999999999", "Leon Green"),
        ("Sarah Chen", "sarah.chen@cedarstone.test", "555-0590", ""),
        ("Priya Nair", "priya.nair@cedarstone.test", "555-0591", ""),
        ("Marcus Johnson", "marcus.johnson@cedarstone.test", "555-0592", ""),
        ("Jamie Bennett", "jamie.bennett@cedarstone.test", "555-0501", ""),
        ("Dakota Rogers", "dakota.rogers@cedarstone.test", "555-0502", ""),
        ("Payton Ross", "payton.ross@cedarstone.test", "555-0503", ""),
        ("Harper Powell", "harper.powell@cedarstone.test", "555-0504", ""),
        ("Arden Long", "arden.long@cedarstone.test", "555-0505", ""),
        ("Marley Patterson", "marley.patterson@cedarstone.test", "555-0506", ""),
        ("Robin Hughes", "robin.hughes@cedarstone.test", "555-0507", ""),
        ("Corey Flores", "corey.flores@cedarstone.test", "555-0508", ""),
        ("Phoenix Washington", "phoenix.washington@cedarstone.test", "555-0509", ""),
        ("Shawn Butler", "shawn.butler@cedarstone.test", "555-0510", ""),
        ("Micah Simmons", "micah.simmons@cedarstone.test", "555-0511", ""),
        ("Charlie Bryant", "charlie.bryant@cedarstone.test", "555-0512", ""),
        ("Elliot Russell", "elliot.russell@cedarstone.test", "555-0513", ""),
        ("Lane Griffin", "lane.griffin@cedarstone.test", "555-0514", ""),
        ("Remy Hamilton", "remy.hamilton@cedarstone.test", "555-0519", ""),
        ("Ellis Graham", "ellis.graham@cedarstone.test", "555-0520", ""),
    ],
}

ADDITIONAL_CONTACT_GIVEN_NAMES = (
    "Adrian",
    "Bianca",
    "Caleb",
    "Delilah",
    "Ethan",
    "Fatima",
    "Gavin",
    "Helena",
    "Isaac",
    "Jasmine",
    "Kieran",
    "Leila",
    "Mateo",
    "Noelle",
    "Owen",
    "Paloma",
    "Rafael",
    "Simone",
    "Tristan",
    "Uma",
    "Victor",
    "Willa",
    "Xavier",
    "Yasmin",
    "Zachary",
)

ADDITIONAL_CONTACT_FAMILY_NAMES = (
    "Armstrong",
    "Bishop",
    "Calderon",
    "Desai",
    "Eriksen",
    "Farrell",
    "Gupta",
    "Haddad",
    "Ingram",
    "Jensen",
    "Kowalski",
    "Laurent",
    "Mendoza",
    "Novak",
    "Okafor",
    "Petrov",
    "Quintero",
    "Romano",
    "Sato",
    "Turner",
    "Usman",
    "Valdez",
    "Williams",
    "Xu",
    "Young",
    "Zimmerman",
    "Bouchard",
    "Costa",
    "Dubois",
    "Fischer",
)

SHARED_EVENTS = [
    ("Weekly Goals", "Alignment on week deliverables."),
    ("Project Sync", "Sync on upcoming milestones."),
    ("Design Review", "Design prototype feedback."),
    ("Client Update", "Prepare presentation materials."),
    ("Retrospective", "End of week reflection."),
    ("Weekly Goals", "Alignment on week deliverables."),
    ("Engineering Standup", "Technical blockers."),
    ("Marketing Overview", "Campaign tracking."),
    ("Quarterly Planning", "Discussion for Q4."),
    ("All Hands", "Company wide meeting."),
    ("Weekly Goals", "Alignment on week deliverables."),
    ("Vendor Meeting", "Software license renewal."),
    ("Security Audit", "IT security overview."),
    ("Budget Review", "Finance touchpoint."),
    ("Team Offsite Prep", "Logistics for Q4."),
]

AGENT_EVENTS = {
    "maya.patel": [
        ("1:1 Manager Sync", "Monthly check-in."),
        ("Mentorship Chat", "Coffee chat with a junior developer."),
        ("Architecture Review", "Review new data models."),
        ("Interviews", "Candidate screening."),
        ("Focus Time", "No-meeting block."),
    ],
    "daniel.brooks": [
        ("1:1 Director Sync", "Quarterly check-in."),
        ("Performance Review", "Self evaluation."),
        ("Training Workshop", "Cloud certification study."),
        ("External Webinar", "Industry trends."),
        ("Focus Time", "No-meeting block."),
    ],
}

PUNCTUAL_EVENTS = [
    ("Invoice Reconciliation Workshop", "Resolve invoice exceptions and confirm the approved accounts-receivable balance."),
    ("Customer Onboarding Session", "Configure the customer workspace and agree the first-month adoption plan."),
    ("Vendor Contract Negotiation", "Review service levels, renewal pricing, and contract responsibilities."),
    ("Launch Readiness Review", "Confirm launch criteria, support coverage, communications, and rollback ownership."),
    ("Candidate Portfolio Interview", "Evaluate a fictional candidate portfolio against the published role criteria."),
    ("Office Safety Briefing", "Review workplace safety procedures and assign follow-up actions."),
    ("Data Migration Rehearsal", "Run the migration checklist against a representative test dataset."),
    ("Product Demonstration", "Demonstrate the latest workflow and collect structured stakeholder feedback."),
    ("Procurement Bid Evaluation", "Score supplier responses and document the recommended shortlist."),
    ("Campaign Creative Approval", "Review final campaign assets, claims, accessibility, and publishing dates."),
    ("Incident Postmortem", "Document the incident timeline, contributing factors, and preventative actions."),
    ("Customer Renewal Planning", "Review customer outcomes and prepare the renewal recommendation."),
    ("Forecast Sign-off", "Approve the revised commercial forecast and record material assumptions."),
    ("Accessibility Review", "Evaluate the current release against accessibility acceptance criteria."),
    ("Warehouse Capacity Planning", "Review inbound volume, staffing, storage capacity, and overflow options."),
    ("Audit Evidence Review", "Check evidence completeness before the scheduled compliance assessment."),
    ("Training Needs Assessment", "Identify capability gaps and prioritize the next training cycle."),
    ("Service Escalation Review", "Agree recovery actions for an escalated customer service case."),
    ("Partnership Discovery Call", "Explore a potential partner integration and define validation questions."),
    ("Content Publishing Review", "Approve the publishing schedule, owners, and quality checklist."),
    ("Expense Policy Q and A", "Clarify expense policy examples and document unresolved questions."),
    ("New Starter Welcome", "Introduce the team, systems, operating rhythm, and first-week objectives."),
    ("Pricing Proposal Review", "Validate proposal scope, pricing assumptions, and approval requirements."),
    ("Quarterly Inventory Count", "Coordinate the physical inventory count and reconciliation process."),
    ("Research Findings Presentation", "Present findings and agree which recommendations move into delivery."),
    ("Contract Handover Session", "Transfer signed obligations, milestones, contacts, and reporting dates."),
    ("Delivery Risk Workshop", "Identify delivery risks and assign practical mitigations and owners."),
    ("Customer Feedback Interview", "Collect detailed feedback about the latest customer workflow."),
    ("Process Automation Discovery", "Map the current process and identify safe automation opportunities."),
    ("Year-End Planning Workshop", "Agree year-end priorities, dependencies, staffing, and decision dates."),
]

CANONICAL_MESSAGES = [
    ("maya.patel", "Hey Daniel, did you get a chance to look at the Q3 marketing report?"),
    ("daniel.brooks", "Yes I did! The numbers look solid, especially the user acquisition metrics."),
    ("maya.patel", "Agreed. We should highlight the social media campaign results in the upcoming board meeting."),
    ("daniel.brooks", "Makes sense. I'll prep a few slides for that. Do we have the final budget numbers from Finance yet?"),
    ("maya.patel", "Not yet, I pinged Sarah about it this morning. She said she'd have them by EOD."),
    ("daniel.brooks", "Okay, let's touch base tomorrow morning to finalize the deck."),
    ("maya.patel", "Sounds good. By the way, the client meeting got moved to next Thursday."),
    ("daniel.brooks", "Got it. I'll update my calendar. Thanks for the heads up!"),
]

BASELINE_TALK_TOPICS: dict[str, tuple[tuple[str, str, str, str], ...]] = {
    "Research Updates": (
        ("the customer interview synthesis", "Three interviews point to the same reporting-navigation problem.", "tag the supporting quotes and compare them with usage data", "the evidence table is reviewed"),
        ("the July usability study", "Participants completed exports quickly but hesitated when saving filters.", "add a filter-saving task to the next prototype test", "the revised test script is approved"),
        ("the competitor workflow review", "Two products surface approval history more clearly than our current design.", "capture screenshots and summarize the useful interaction patterns", "the comparison note is published"),
        ("the survey response analysis", "Response quality is good, although the operations segment is underrepresented.", "invite five more operations respondents", "the sample reaches the agreed balance"),
        ("the research repository cleanup", "Six recent studies are missing decision links and final summaries.", "ask each study owner to complete the repository fields", "all six records are complete"),
        ("the accessibility interview findings", "Keyboard users consistently requested a clearer focus location after dialogs close.", "add the behavior to the interaction recommendation", "Design and Engineering confirm the recommendation"),
    ),
    "Operations Planning": (
        ("next week's fulfillment plan", "Inbound volume is above forecast on Tuesday and Wednesday.", "move one packing shift to the midweek window", "the revised roster is confirmed"),
        ("the service escalation queue", "Four cases are waiting on customer evidence rather than internal action.", "send a consolidated evidence request to each account owner", "all owners acknowledge their requests"),
        ("the inventory reconciliation", "The variance is limited to two bins with recent manual adjustments.", "recount both bins and attach the adjustment records", "Finance accepts the reconciliation"),
        ("the weekend maintenance runbook", "The rollback owner and customer notification timing are still unclear.", "name the rollback lead and add notification checkpoints", "the change manager approves the runbook"),
        ("the supplier delivery schedule", "One component arrives two days after the planned assembly start.", "sequence unaffected work first and confirm expedited shipping", "the updated schedule has no blocked shift"),
        ("the monthly capacity forecast", "Support demand is trending eight percent above the current staffing plan.", "model an additional evening rotation", "Operations signs off on the coverage plan"),
    ),
    "Product Coordination": (
        ("the account export improvement", "Engineering confirmed the new columns fit the existing export pipeline.", "finalize column labels and acceptance examples", "the delivery ticket is ready for implementation"),
        ("the mobile approval flow", "The current prototype needs one fewer confirmation step for low-risk requests.", "test the simplified path with compliance stakeholders", "the control design is accepted"),
        ("the release candidate checklist", "All critical scenarios pass, while two help links still point to draft pages.", "publish the help pages and rerun link validation", "release management signs off"),
        ("the notification preference design", "Customers want separate controls for assignments and status changes.", "split the preference options in the specification", "the updated behavior is estimated"),
        ("the dashboard performance work", "The slowest query is the unbounded regional comparison.", "add the proposed default date range", "the performance test meets its target"),
        ("the next-quarter roadmap", "Two initiatives depend on the same data-platform migration window.", "sequence their discovery and delivery milestones", "the dependency plan is reflected in the roadmap"),
    ),
    "Design Exchange": (
        ("the invoice review prototype", "The revised totals hierarchy makes exceptions easier to scan.", "test the design with two finance specialists", "the validation notes are incorporated"),
        ("the customer portal navigation", "The new labels are clearer, but the support link is still difficult to find.", "move support into the persistent account menu", "the navigation review is approved"),
        ("the empty-state illustration set", "The illustrations are consistent, although two messages do not explain the next action.", "rewrite those messages with direct recovery steps", "Content Design approves the set"),
        ("the analytics color palette", "Two categorical colors are too similar in common color-vision simulations.", "replace the weaker color and rerun contrast checks", "the accessibility review passes"),
        ("the presentation template refresh", "The title and data slides are ready; the case-study layout needs more room for outcomes.", "simplify the side panel and enlarge the result area", "the template owner publishes the update"),
        ("the mobile component audit", "Spacing is consistent except in compact selection lists.", "align the compact list tokens with the design system", "the component library release includes the fix"),
    ),
}

ADDITIONAL_TALK_TOPICS: dict[str, tuple[tuple[str, str, str, str], ...]] = {
    "Finance and Invoices": (
        ("the July invoice register", "Two customer references are missing purchase-order numbers.", "contact the account owners before the billing cutoff", "both references are attached"),
        ("the travel expense batch", "Three receipts need a clearer business-purpose note.", "return those claims for clarification", "the updated notes are approved"),
        ("the accounts-receivable aging sheet", "The oldest balance belongs to a customer that already confirmed payment.", "check the bank feed before sending another reminder", "the payment is matched"),
        ("next quarter's software budget", "Renewal pricing is slightly above the planning assumption.", "request a revised quote and update the forecast", "Finance signs off on the revised amount"),
        ("the supplier credit memo", "The amount matches the damaged shipment report.", "apply it against the open vendor invoice", "the vendor balance is reconciled"),
        ("the month-end close checklist", "Most tasks are complete, but payroll allocation is still pending.", "ask People Operations for the final allocation file", "the allocation posts successfully"),
    ),
    "Customer Launches": (
        ("Alder Grove Retail onboarding", "The workspace is configured and the administrator list is confirmed.", "schedule the reporting walkthrough", "the customer completes the walkthrough"),
        ("Blue Harbor Foods data import", "The sample file passes validation except for two date columns.", "share the corrected date format with their analyst", "the revised import completes"),
        ("Everfield Labs launch plan", "Training attendance is strong, but support coverage needs one more owner.", "assign a backup escalation contact", "the escalation rota is published"),
        ("Maple Ridge Supply acceptance test", "Order search and exports passed; one dashboard filter needs adjustment.", "update the filter and rerun the scenario", "the customer signs the acceptance note"),
        ("Silver Fern Travel administrator training", "The team requested an extra example for recurring reports.", "add that example to the training workbook", "the workbook is shared"),
        ("Willow and Pine Design launch communications", "The draft announcement is ready for brand review.", "send it to the customer communications lead", "the announcement is approved"),
    ),
    "Office Operations": (
        ("the meeting-room equipment check", "Cedar is ready, while Harbor needs a replacement display cable.", "open a facilities request for the cable", "the replacement is installed"),
        ("the visitor access process", "Reception needs the attendee list by 3 PM on the prior business day.", "add that deadline to the event checklist", "the checklist is republished"),
        ("next week's catering order", "Dietary requirements are confirmed for all but two attendees.", "follow up with the two meeting organizers", "the final quantities are sent"),
        ("the quarterly supply count", "Printer paper is below the reorder point, while other supplies are sufficient.", "place the approved replenishment order", "the delivery date is confirmed"),
        ("the office maintenance window", "Facilities can complete the work on Friday after 6 PM.", "notify the teams using the affected floor", "all floor contacts acknowledge the notice"),
        ("the emergency contact sheet", "Two team contacts changed roles this month.", "confirm their replacements with People Operations", "the updated sheet is posted"),
    ),
    "Hiring Coordination": (
        ("the operations analyst interview loop", "All interviewers submitted availability for Thursday.", "publish the final interview schedule", "the candidate receives the schedule"),
        ("the customer success scorecard", "The communication examples need a clearer scoring anchor.", "add examples for strong and developing responses", "the panel approves the revision"),
        ("the design portfolio review", "The panel wants thirty additional minutes for the case-study discussion.", "extend the final interview block", "the updated invitation is accepted"),
        ("the new starter equipment request", "The laptop is reserved, but the headset selection is still open.", "confirm the preferred headset with the manager", "the complete kit is assigned"),
        ("the finance coordinator reference check", "One reference is complete and the second call is booked.", "record the second response after the call", "both references are documented"),
        ("next month's onboarding cohort", "Four starters are confirmed across three teams.", "combine their shared orientation sessions", "the orientation calendar is published"),
    ),
    "Events and Travel": (
        ("the customer workshop agenda", "The customer asked for more time on reporting workflows.", "shorten the introduction and extend the hands-on section", "the facilitator approves the agenda"),
        ("the regional team offsite", "The venue can accommodate the revised attendance estimate.", "confirm the room layout and accessibility needs", "the venue issues final confirmation"),
        ("conference travel bookings", "Most flights are within policy, but one route needs manager approval.", "send the exception with the lower-cost comparison", "the travel exception is approved"),
        ("the partner dinner reservation", "The restaurant confirmed the private room and dietary options.", "share the final guest count on Friday", "the reservation is reconfirmed"),
        ("the product webinar rehearsal", "Audio and screen sharing passed, but the closing slide needs an updated link.", "replace the link before the final rehearsal", "the producer verifies the updated deck"),
        ("the training-room schedule", "Two sessions currently overlap in Meeting Room Harbor.", "move the smaller session to Cedar", "both facilitators accept the change"),
    ),
}

NOTIFICATION_BLUEPRINTS = (
    (
        "invoice-review",
        "Sarah Chen",
        "requested your review of {file_name}",
        "Finance/Invoices/",
        "Finance and Invoices",
        "Confirm the totals and approval status, then post the decision in {room}.",
    ),
    (
        "purchase-order-delivery",
        "Marcus Johnson",
        "flagged a delivery question on {file_name}",
        "Procurement/Purchase Orders/",
        "Office Operations",
        "Check the required date and delivery instructions before replying in {room}.",
    ),
    (
        "vendor-assessment",
        "Priya Nair",
        "updated the assessment notes for {file_name}",
        "Procurement/Vendor Assessments/",
        "Operations Planning",
        "Review the score and supporting order history, then record any follow-up in {room}.",
    ),
    (
        "management-report",
        "Leon Greene",
        "commented on {file_name}",
        "Reports/Monthly Management/",
        "Research Updates",
        "Validate the highlighted metric and respond in {room} before the report is finalized.",
    ),
    (
        "quarterly-review",
        "Sarah Chen",
        "asked for slide approval on {file_name}",
        "Presentations/Quarterly Reviews/",
        "Design Exchange",
        "Review the conclusions and approve or annotate the deck in {room}.",
    ),
    (
        "customer-order",
        "Leon Greene",
        "reported a customer change in {file_name}",
        "Sales/Orders/",
        "Customer Launches",
        "Check the order details against the launch plan and confirm the change in {room}.",
    ),
    (
        "candidate-review",
        "Priya Nair",
        "added interview feedback to {file_name}",
        "People/Recruiting/",
        "Hiring Coordination",
        "Review the feedback and add your recommendation to {room}.",
    ),
    (
        "meeting-follow-up",
        "Marcus Johnson",
        "posted follow-up notes in {file_name}",
        "Meetings/Meeting Reports/",
        "Events and Travel",
        "Confirm your assigned action and note any scheduling conflict in {room}.",
    ),
    (
        "project-milestone",
        "Sarah Chen",
        "changed a milestone owner in {file_name}",
        "Projects/Status Reports/",
        "Product Coordination",
        "Review the new owner and due date, then acknowledge the handoff in {room}.",
    ),
    (
        "budget-check",
        "Leon Greene",
        "requested a budget check on {file_name}",
        "Finance/Budgets/",
        "Finance and Invoices",
        "Compare the forecast with the related invoice totals and share your conclusion in {room}.",
    ),
    (
        "inventory-variance",
        "Marcus Johnson",
        "reported an inventory variance in {file_name}",
        "Operations/Inventory/",
        "Operations Planning",
        "Verify the quantity and location fields, then assign the correction in {room}.",
    ),
    (
        "contract-review",
        "Priya Nair",
        "requested a legal review of {file_name}",
        "Legal/Contracts/",
        "Project Alpha",
        "Check the renewal and approval clauses before the next Project Alpha decision.",
    ),
)

GENERATED_DOCUMENTS = {
    "Marketing Assistant Resume.docx": (
        "Marketing Assistant Resume",
        "Candidate: Jamie Example\nExperience: Community campaigns, editorial calendars, and analytics.\n"
        "Education: B.A. Communications\nThis fictional resume contains no real personal information.",
    ),
    "Marketing Assistant Resume-2.docx": (
        "Marketing Assistant Resume - Copy",
        "Candidate: Jamie Example\nExperience: Community campaigns, editorial calendars, and analytics.\n"
        "Education: B.A. Communications\nThis fictional resume contains no real personal information.",
    ),
    "Marketing Assistant Resume.pdf": (
        "Marketing Assistant Resume",
        "Candidate: Jamie Example. Experience in campaigns and analytics. Fictional research data.",
    ),
    "chloroplastmarketingstrategy.docx": (
        "Chloroplast Marketing Strategy",
        "A fictional campaign brief for a classroom product launch and audience research exercise.",
    ),
    "clientmeetingmemo.docx": (
        "Client Meeting Memo",
        "Synthetic discussion notes covering agenda ownership, review milestones, and follow-up actions.",
    ),
    "clientmeetingmemo.pdf": (
        "Client Meeting Memo",
        "Synthetic discussion notes covering agenda ownership, review milestones, and follow-up actions.",
    ),
    "sample essay.docx": (
        "Sample Essay",
        "A synthetic essay about responsible collaboration, reproducible research, and careful documentation.",
    ),
}

BUSINESS_FOLDERS = (
    "Analytics",
    "Finance",
    "Legal",
    "Marketing",
    "Meetings",
    "Operations",
    "People",
    "Presentations",
    "Procurement",
    "Projects",
    "Reports",
    "Sales",
    "Strategy",
)

CUSTOMERS = (
    "Alder Grove Retail",
    "Blue Harbor Foods",
    "Copperline Studio",
    "Everfield Labs",
    "Juniper Works",
    "Maple Ridge Supply",
    "Redstone Health",
    "Silver Fern Travel",
    "Suncrest Market",
    "Willow and Pine Design",
)

VENDORS = (
    "Atlas Office Services",
    "Brightpath Logistics",
    "Clearwater Packaging",
    "Greenline Technology",
    "Harborview Catering",
    "Northstar Facilities",
    "Oakstone Printing",
    "Summit Cloud Systems",
)

VENDOR_DETAILS: dict[str, dict[str, str]] = {
    "Atlas Office Services": {"vendor_id": "VEN-001", "category": "Office supplies"},
    "Brightpath Logistics": {"vendor_id": "VEN-002", "category": "Logistics and freight"},
    "Clearwater Packaging": {"vendor_id": "VEN-003", "category": "Packaging materials"},
    "Greenline Technology": {"vendor_id": "VEN-004", "category": "Information technology"},
    "Harborview Catering": {"vendor_id": "VEN-005", "category": "Catering and hospitality"},
    "Northstar Facilities": {"vendor_id": "VEN-006", "category": "Facilities services"},
    "Oakstone Printing": {"vendor_id": "VEN-007", "category": "Printing and production"},
    "Summit Cloud Systems": {"vendor_id": "VEN-008", "category": "Cloud services"},
}

PROJECTS = (
    "Aurora Launch",
    "Beacon Migration",
    "Cedar Renewal",
    "Delta Mobile",
    "Evergreen Portal",
    "Horizon Analytics",
    "Juniper Onboarding",
    "Meridian Expansion",
    "Nova Commerce",
    "Orion Service Desk",
)

TEAMS = (
    "Commercial Operations",
    "Customer Experience",
    "Finance and Planning",
    "People Operations",
    "Product Delivery",
    "Revenue Operations",
    "Service Reliability",
    "Supply and Fulfillment",
)

BUSINESS_NAMES = (
    "Avery Brooks",
    "Morgan Reed",
    "Jordan Kim",
    "Riley Patel",
    "Cameron Price",
    "Taylor Nguyen",
    "Casey Morgan",
    "Parker Evans",
    "Quinn Foster",
    "Drew Howard",
)

TIMESHEET_WORKERS: dict[str, tuple[str, ...]] = {
    "Full-Time Employees": ("Avery Brooks", "Morgan Reed", "Jordan Kim", "Riley Patel"),
    "Part-Time Employees": ("Cameron Price", "Taylor Nguyen", "Casey Morgan", "Parker Evans"),
    "Contractors": ("Quinn Foster", "Drew Howard", "Alex Morgan", "Jamie Chen"),
    "Interns": ("Sam Rivera", "Robin Shah", "Mia Laurent", "Noah Bennett"),
    "Temporary Staff": ("Ella Hughes", "Lucas Martin", "Zoe Clark", "Ethan Wilson"),
    "Consultants": ("Maya Singh", "Owen Davis", "Sofia Rossi", "Liam Walker"),
}

PRODUCTS = (
    ("Implementation workshop", 850),
    ("Analytics workspace license", 240),
    ("Customer onboarding package", 620),
    ("Data quality assessment", 475),
    ("Managed support block", 390),
    ("Operations dashboard module", 710),
    ("Process documentation service", 330),
    ("Quarterly optimization review", 560),
    ("Remote training session", 275),
    ("Workflow integration connector", 445),
)

PURCHASE_ORDER_ITEMS = (
    ("OFF-1042", "A4 recycled copy paper, 80 gsm, case", 46),
    ("OFF-1178", "Black gel pens, box of 24", 28),
    ("OFF-1305", "Hardcover project notebook, pack of 6", 54),
    ("OFF-1451", "Desktop document organizer", 39),
    ("IT-2044", "USB-C docking station", 189),
    ("IT-2190", "Wireless keyboard and mouse set", 76),
    ("IT-2375", "27-inch business monitor", 318),
    ("IT-2512", "Encrypted portable SSD, 1 TB", 164),
    ("IT-2688", "Noise-cancelling office headset", 142),
    ("FAC-3021", "Ergonomic task chair", 425),
    ("FAC-3157", "Height-adjustable desk converter", 286),
    ("FAC-3299", "LED desk lamp with USB charging", 63),
    ("FAC-3410", "Meeting-room whiteboard, magnetic", 214),
    ("PKG-4055", "Recyclable shipping cartons, bundle", 72),
    ("PKG-4192", "Paper packing tape, case", 58),
    ("PKG-4270", "Thermal shipping labels, 12 rolls", 96),
    ("OPS-5018", "Barcode scanner with charging stand", 239),
    ("OPS-5164", "Warehouse safety vest, pack of 10", 85),
    ("OPS-5293", "Inventory shelf label kit", 67),
    ("OPS-5438", "Mobile equipment inspection kit", 175),
)

BUSINESS_DOCUMENT_PROFILES: dict[str, tuple[dict[str, str], ...]] = {
    "txt": (
        {"area": "Operations", "category": "Daily Operations", "kind": "operations", "label": "Operations Shift Handoff", "prefix": "OPS"},
        {"area": "Sales", "category": "Account Notes", "kind": "customer", "label": "Customer Account Note", "prefix": "ACCT"},
        {"area": "People", "category": "Recruiting", "kind": "people", "label": "Interview Debrief", "prefix": "INT"},
    ),
    "md": (
        {"area": "Finance", "category": "Budgets", "kind": "report", "label": "Budget Commentary", "prefix": "BUDNOTE"},
        {"area": "Legal", "category": "Contracts", "kind": "report", "label": "Contract Review Notes", "prefix": "LEGAL"},
        {"area": "Meetings", "category": "Minutes", "kind": "meeting", "label": "Meeting Minutes", "prefix": "MTG"},
        {"area": "Projects", "category": "Status Reports", "kind": "project", "label": "Project Status Report", "prefix": "PRJ"},
        {"area": "Operations", "category": "Procedures", "kind": "operations", "label": "Standard Operating Procedure", "prefix": "SOP"},
        {"area": "Marketing", "category": "Campaigns", "kind": "report", "label": "Campaign Brief", "prefix": "MKT"},
        {"area": "People", "category": "Training", "kind": "people", "label": "Team Training Plan", "prefix": "TRN"},
        {"area": "Strategy", "category": "Plans", "kind": "project", "label": "Strategic Initiative Brief", "prefix": "STRAT"},
    ),
    "csv": (
        {"area": "Sales", "category": "Orders", "kind": "transaction", "label": "Sales Order Register", "prefix": "SO"},
        {"area": "Finance", "category": "Invoice Registers", "kind": "transaction", "label": "Invoice Register", "prefix": "INVREG"},
        {"area": "Operations", "category": "Inventory", "kind": "inventory", "label": "Inventory Count", "prefix": "STOCK"},
        {"area": "Reports", "category": "Marketing Performance", "kind": "report", "label": "Campaign Performance", "prefix": "PERF"},
    ),
    "json": (
        {"area": "Legal", "category": "Contracts", "kind": "report", "label": "Contract Clause Register", "prefix": "CLAUSE"},
        {"area": "Operations", "category": "Workflow Data", "kind": "operations", "label": "Workflow Configuration", "prefix": "WFLOW"},
        {"area": "Finance", "category": "Expenses", "kind": "transaction", "label": "Expense Claim", "prefix": "EXP"},
        {"area": "Operations", "category": "Shipments", "kind": "inventory", "label": "Shipment Manifest", "prefix": "SHIP"},
        {"area": "Strategy", "category": "Plans", "kind": "report", "label": "Strategy Decision Register", "prefix": "SDEC"},
    ),
    "pdf": (
        {"area": "Finance", "category": "Invoices", "kind": "transaction", "label": "Customer Invoice", "prefix": "INV"},
        {"area": "Finance", "category": "Budgets", "kind": "report", "label": "Budget Review", "prefix": "BUDREV"},
        {"area": "Legal", "category": "Contracts", "kind": "report", "label": "Contract Approval Summary", "prefix": "CONTRACT"},
        {"area": "Finance", "category": "Payment Notices", "kind": "transaction", "label": "Payment Notice", "prefix": "PAY"},
        {"area": "Reports", "category": "Monthly Management", "kind": "report", "label": "Monthly Management Report", "prefix": "MMR"},
        {"area": "Finance", "category": "Account Statements", "kind": "transaction", "label": "Account Statement", "prefix": "STM"},
        {"area": "Reports", "category": "Compliance", "kind": "report", "label": "Compliance Audit Summary", "prefix": "AUD"},
        {"area": "Operations", "category": "Deliveries", "kind": "inventory", "label": "Delivery Confirmation", "prefix": "DEL"},
    ),
    "docx": (
        {"area": "Legal", "category": "Contracts", "kind": "report", "label": "Contract Review", "prefix": "CTR"},
        {"area": "Meetings", "category": "Meeting Reports", "kind": "meeting", "label": "Meeting Report", "prefix": "MREP"},
        {"area": "Projects", "category": "Proposals", "kind": "project", "label": "Project Proposal", "prefix": "PROP"},
        {"area": "Reports", "category": "Quarterly Business", "kind": "report", "label": "Quarterly Business Report", "prefix": "QBR"},
        {"area": "Sales", "category": "Client Briefs", "kind": "customer", "label": "Client Account Brief", "prefix": "BRIEF"},
        {"area": "Operations", "category": "Procedures", "kind": "operations", "label": "Operations Procedure", "prefix": "PROC"},
        {"area": "Strategy", "category": "Plans", "kind": "project", "label": "Strategy Memo", "prefix": "SMEMO"},
    ),
    "xlsx": (
        {"area": "Sales", "category": "Pipeline", "kind": "customer", "label": "Sales Pipeline", "prefix": "PIPE"},
        {"area": "Finance", "category": "Budgets", "kind": "report", "label": "Budget Forecast", "prefix": "BUD"},
        {"area": "Finance", "category": "Accounts Receivable", "kind": "transaction", "label": "Invoice Aging", "prefix": "AGING"},
        {"area": "Operations", "category": "Inventory", "kind": "inventory", "label": "Inventory Forecast", "prefix": "FORECAST"},
        {"area": "Sales", "category": "Order Tracking", "kind": "transaction", "label": "Order Tracker", "prefix": "TRACK"},
        {"area": "Strategy", "category": "Plans", "kind": "report", "label": "Scenario Planning Model", "prefix": "SCEN"},
    ),
    "pptx": (
        {"area": "Presentations", "category": "Quarterly Reviews", "kind": "report", "label": "Quarterly Business Review", "prefix": "DECK"},
        {"area": "Presentations", "category": "Project Kickoffs", "kind": "project", "label": "Project Kickoff", "prefix": "KICK"},
        {"area": "Presentations", "category": "Sales Proposals", "kind": "customer", "label": "Sales Proposal", "prefix": "SALE"},
        {"area": "Presentations", "category": "Operations Reviews", "kind": "operations", "label": "Operations Review", "prefix": "OREV"},
        {"area": "Presentations", "category": "Campaign Plans", "kind": "report", "label": "Campaign Plan", "prefix": "CAMP"},
        {"area": "Strategy", "category": "Plans", "kind": "project", "label": "Strategy Review", "prefix": "SREV"},
    ),
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def zip_bytes(parts: dict[str, str | bytes]) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in sorted(parts):
            value = parts[name]
            payload = value.encode("utf-8") if isinstance(value, str) else value
            info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload)
    return stream.getvalue()


def make_docx(title: str, body: str) -> bytes:
    paragraphs = [title, *body.splitlines()]
    document = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{xml_escape(line)}</w:t></w:r></w:p>'
        for line in paragraphs
    )
    return zip_bytes(
        {
            "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
            "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
            "word/document.xml": f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>{document}<w:sectPr/></w:body></w:document>""",
        }
    )


def make_xlsx(
    title: str,
    sheet_name: str,
    columns: list[str],
    data_rows: list[list[str | int | float]],
    metadata: dict[str, str],
) -> bytes:
    def column_name(index: int) -> str:
        result = ""
        while index:
            index, remainder = divmod(index - 1, 26)
            result = chr(65 + remainder) + result
        return result

    def cell(reference: str, value: str | int | float) -> str:
        if isinstance(value, (int, float)):
            return f'<c r="{reference}"><v>{value}</v></c>'
        return f'<c r="{reference}" t="inlineStr"><is><t>{xml_escape(str(value))}</t></is></c>'

    worksheet_rows = [f'<row r="1">{cell("A1", title)}</row>']
    row_number = 2
    for label, value in metadata.items():
        worksheet_rows.append(
            f'<row r="{row_number}">{cell(f"A{row_number}", label)}{cell(f"B{row_number}", value)}</row>'
        )
        row_number += 1
    row_number += 1
    header_row = row_number
    worksheet_rows.append(
        f'<row r="{row_number}">'
        + "".join(cell(f"{column_name(index)}{row_number}", value) for index, value in enumerate(columns, start=1))
        + "</row>"
    )
    for values in data_rows:
        row_number += 1
        worksheet_rows.append(
            f'<row r="{row_number}">'
            + "".join(cell(f"{column_name(index)}{row_number}", value) for index, value in enumerate(values, start=1))
            + "</row>"
        )
    final_column = column_name(max(1, len(columns)))
    safe_sheet_name = sheet_name[:31]
    return zip_bytes(
        {
            "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""",
            "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
            "xl/workbook.xml": f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{xml_escape(safe_sheet_name)}" sheetId="1" r:id="rId1"/></sheets></workbook>""",
            "xl/_rels/workbook.xml.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>""",
            "xl/worksheets/sheet1.xml": f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><cols><col min="1" max="{len(columns)}" width="22" customWidth="1"/></cols><sheetData>{''.join(worksheet_rows)}</sheetData><autoFilter ref="A{header_row}:{final_column}{row_number}"/></worksheet>""",
        }
    )


def make_timesheet_xlsx(
    title: str,
    period: str,
    owner: str,
    category_rows: dict[str, list[list[str | int | float]]],
) -> bytes:
    def column_name(index: int) -> str:
        result = ""
        while index:
            index, remainder = divmod(index - 1, 26)
            result = chr(65 + remainder) + result
        return result

    def cell(reference: str, value: str | int | float) -> str:
        if isinstance(value, (int, float)):
            return f'<c r="{reference}"><v>{value}</v></c>'
        return f'<c r="{reference}" t="inlineStr"><is><t>{xml_escape(str(value))}</t></is></c>'

    columns = [
        "Employee ID",
        "Employee Name",
        "Worker Category",
        "Cost Center",
        "Regular Hours",
        "Overtime Hours",
        "Leave Hours",
        "Total Hours",
        "Approval Status",
    ]
    sheet_names = list(category_rows)
    if not sheet_names or len(sheet_names) != len(set(sheet_names)):
        raise ValueError("Timesheet worker categories must be non-empty and unique")

    overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, len(sheet_names) + 1)
    )
    workbook_sheets = "".join(
        f'<sheet name="{xml_escape(name[:31])}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheet_names, start=1)
    )
    workbook_relationships = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, len(sheet_names) + 1)
    )
    parts: dict[str, str | bytes] = {
        "[Content_Types].xml": f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
{overrides}</Types>""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        "xl/workbook.xml": f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>{workbook_sheets}</sheets></workbook>""",
        "xl/_rels/workbook.xml.rels": f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{workbook_relationships}</Relationships>""",
    }

    for sheet_index, (category, data_rows) in enumerate(category_rows.items(), start=1):
        worksheet_rows = [f'<row r="1">{cell("A1", title)}</row>']
        metadata = (
            ("Worker Category", category),
            ("Period", period),
            ("Prepared For", owner),
            ("Approval Cycle", "Monthly"),
        )
        row_number = 2
        for label, value in metadata:
            worksheet_rows.append(
                f'<row r="{row_number}">{cell(f"A{row_number}", label)}{cell(f"B{row_number}", value)}</row>'
            )
            row_number += 1
        row_number += 1
        header_row = row_number
        worksheet_rows.append(
            f'<row r="{row_number}">'
            + "".join(cell(f"{column_name(index)}{row_number}", value) for index, value in enumerate(columns, start=1))
            + "</row>"
        )
        for values in data_rows:
            row_number += 1
            worksheet_rows.append(
                f'<row r="{row_number}">'
                + "".join(cell(f"{column_name(index)}{row_number}", value) for index, value in enumerate(values, start=1))
                + "</row>"
            )
        data_end_row = row_number
        row_number += 1
        totals = [
            "CATEGORY TOTAL",
            "",
            category,
            "",
            sum(int(row[4]) for row in data_rows),
            sum(int(row[5]) for row in data_rows),
            sum(int(row[6]) for row in data_rows),
            sum(int(row[7]) for row in data_rows),
            "Reviewed",
        ]
        worksheet_rows.append(
            f'<row r="{row_number}">'
            + "".join(cell(f"{column_name(index)}{row_number}", value) for index, value in enumerate(totals, start=1))
            + "</row>"
        )
        parts[f"xl/worksheets/sheet{sheet_index}.xml"] = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><cols><col min="1" max="9" width="22" customWidth="1"/></cols><sheetData>{''.join(worksheet_rows)}</sheetData><autoFilter ref="A{header_row}:I{data_end_row}"/></worksheet>"""
    return zip_bytes(parts)


def make_pptx(title: str, slides: list[tuple[str, list[str]]]) -> bytes:
    def shape(shape_id: int, name: str, lines: list[str], y: int, height: int) -> str:
        paragraphs = "".join(
            f'<a:p><a:r><a:rPr lang="en-US"/><a:t>{xml_escape(line)}</a:t></a:r><a:endParaRPr lang="en-US"/></a:p>'
            for line in lines
        )
        return f"""<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="{xml_escape(name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
<p:spPr><a:xfrm><a:off x="685800" y="{y}"/><a:ext cx="7772400" cy="{height}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/></p:spPr>
<p:txBody><a:bodyPr/><a:lstStyle/>{paragraphs}</p:txBody></p:sp>"""

    if not slides:
        raise ValueError("A presentation must contain at least one slide")
    parts: dict[str, str | bytes] = {
        "[Content_Types].xml": f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
{''.join(f'<Override PartName="/ppt/slides/slide{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>' for index in range(1, len(slides) + 1))}</Types>""",
            "_rels/.rels": """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/></Relationships>""",
            "ppt/presentation.xml": f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldIdLst>{''.join(f'<p:sldId id="{255 + index}" r:id="rId{index}"/>' for index in range(1, len(slides) + 1))}</p:sldIdLst><p:sldSz cx="9144000" cy="5143500"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>""",
            "ppt/_rels/presentation.xml.rels": f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{''.join(f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{index}.xml"/>' for index in range(1, len(slides) + 1))}</Relationships>""",
    }
    for index, (slide_title, bullets) in enumerate(slides, start=1):
        slide_shapes = shape(2, "Title", [slide_title], 457200, 914400) + shape(3, "Body", bullets, 1371600, 3200400)
        parts[f"ppt/slides/slide{index}.xml"] = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld name="{xml_escape(title)}"><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr/>{slide_shapes}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"""
    return zip_bytes(parts)


def make_pdf(title: str, body: str) -> bytes:
    lines: list[str] = []
    for source_line in [title, "", *body.splitlines()]:
        if not source_line:
            lines.append("")
        else:
            lines.extend(textwrap.wrap(source_line, width=92) or [""])
    lines = lines[:46]
    commands = ["BT", "/F1 10 Tf", "54 756 Td"]
    for index, line in enumerate(lines):
        if index:
            commands.append("0 -14 Td")
        safe_line = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append(f"({safe_line}) Tj")
    commands.append("ET")
    content = "\n".join(commands).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    payload = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{number} 0 obj\n".encode())
        payload.extend(obj)
        payload.extend(b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode())
    payload.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(payload)


INVOICE_TEMPLATES = (
    "Modern Banner",
    "Classic Border",
    "Compact Sidebar",
    "Professional Services",
    "Retail Statement",
)

PURCHASE_ORDER_TEMPLATES = (
    "Modern Procurement",
    "Classic Purchase Form",
    "Vendor Sidebar",
    "Operations Grid",
    "Executive Approval",
)


def pdf_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_invoice_pdf(context: dict[str, Any], template_name: str) -> bytes:
    commands: list[str] = []

    def text(
        x: int,
        y: int,
        size: int,
        value: str,
        *,
        bold: bool = False,
        color: tuple[float, float, float] = (0, 0, 0),
    ) -> None:
        red, green, blue = color
        commands.extend(
            [
                "BT",
                f"{red:.3f} {green:.3f} {blue:.3f} rg",
                f"/{'F2' if bold else 'F1'} {size} Tf",
                f"1 0 0 1 {x} {y} Tm",
                f"({pdf_literal(value)}) Tj",
                "ET",
            ]
        )

    def rectangle(
        x: int,
        y: int,
        width: int,
        height: int,
        color: tuple[float, float, float],
        *,
        stroke: bool = False,
    ) -> None:
        red, green, blue = color
        commands.append(f"{red:.3f} {green:.3f} {blue:.3f} {'RG' if stroke else 'rg'}")
        commands.append(f"{x} {y} {width} {height} re {'S' if stroke else 'f'}")

    def line(x1: int, y1: int, x2: int, y2: int, color: tuple[float, float, float]) -> None:
        red, green, blue = color
        commands.extend([f"{red:.3f} {green:.3f} {blue:.3f} RG", f"{x1} {y1} m {x2} {y2} l S"])

    palette = {
        "Modern Banner": (0.10, 0.29, 0.48),
        "Classic Border": (0.25, 0.25, 0.25),
        "Compact Sidebar": (0.12, 0.48, 0.43),
        "Professional Services": (0.37, 0.24, 0.52),
        "Retail Statement": (0.73, 0.31, 0.16),
    }
    accent = palette[template_name]
    invoice_number = context["invoice_number"]
    seller = context["seller"]
    customer = context["customer"]

    if template_name == "Modern Banner":
        rectangle(0, 700, 612, 92, accent)
        text(42, 752, 24, "INVOICE", bold=True, color=(1, 1, 1))
        text(42, 729, 11, seller, bold=True, color=(1, 1, 1))
        text(422, 752, 11, invoice_number, bold=True, color=(1, 1, 1))
        metadata_y = 674
        table_y = 540
    elif template_name == "Classic Border":
        rectangle(24, 24, 564, 744, accent, stroke=True)
        text(240, 738, 22, "INVOICE", bold=True)
        text(42, 708, 14, seller, bold=True)
        line(42, 692, 570, 692, accent)
        text(430, 708, 10, invoice_number)
        metadata_y = 662
        table_y = 530
    elif template_name == "Compact Sidebar":
        rectangle(0, 0, 122, 792, accent)
        text(20, 742, 18, "INVOICE", bold=True, color=(1, 1, 1))
        text(20, 710, 8, invoice_number, bold=True, color=(1, 1, 1))
        text(145, 742, 16, seller, bold=True, color=accent)
        metadata_y = 690
        table_y = 520
    elif template_name == "Professional Services":
        rectangle(36, 720, 540, 48, (0.94, 0.92, 0.96))
        text(48, 738, 18, "SERVICE INVOICE", bold=True, color=accent)
        text(405, 738, 10, invoice_number, bold=True)
        text(48, 695, 13, seller, bold=True)
        metadata_y = 661
        table_y = 520
    else:
        text(42, 744, 13, seller, bold=True)
        text(430, 738, 24, "INVOICE", bold=True, color=accent)
        rectangle(42, 682, 528, 34, (0.98, 0.94, 0.91))
        text(52, 694, 10, f"Invoice {invoice_number}   |   Status: {context['invoice_status']}", bold=True)
        metadata_y = 654
        table_y = 510

    content_x = 145 if template_name == "Compact Sidebar" else 42
    right_x = 390 if template_name == "Compact Sidebar" else 380
    text(content_x, metadata_y, 9, "BILL TO", bold=True, color=accent)
    text(content_x, metadata_y - 16, 11, customer, bold=True)
    text(content_x, metadata_y - 31, 9, f"accounts@{filename_slug(customer).lower()}.cedarstone.test")
    text(content_x, metadata_y - 46, 9, "100 Market Street, Toronto, Ontario")
    text(right_x, metadata_y, 9, "INVOICE DETAILS", bold=True, color=accent)
    text(right_x, metadata_y - 16, 9, f"Issued: {context['record_date']}")
    text(right_x, metadata_y - 31, 9, f"Due: {context['due_date']}")
    text(right_x, metadata_y - 46, 9, f"Terms: {context['payment_terms']}")

    table_x = content_x
    table_width = 570 - table_x
    rectangle(table_x, table_y, table_width, 24, accent)
    text(table_x + 8, table_y + 8, 9, "DESCRIPTION", bold=True, color=(1, 1, 1))
    text(table_x + table_width - 178, table_y + 8, 9, "QTY", bold=True, color=(1, 1, 1))
    text(table_x + table_width - 126, table_y + 8, 9, "RATE", bold=True, color=(1, 1, 1))
    text(table_x + table_width - 64, table_y + 8, 9, "AMOUNT", bold=True, color=(1, 1, 1))

    row_y = table_y - 20
    for index, item in enumerate(context["line_items"][:6]):
        if index % 2:
            rectangle(table_x, row_y - 5, table_width, 18, (0.96, 0.96, 0.96))
        text(table_x + 8, row_y, 8, item["description"][:38])
        text(table_x + table_width - 172, row_y, 8, str(item["quantity"]))
        text(table_x + table_width - 130, row_y, 8, f"${item['unit_price']:.2f}")
        text(table_x + table_width - 68, row_y, 8, f"${item['line_total']:.2f}")
        row_y -= 20
    line(table_x, row_y + 8, table_x + table_width, row_y + 8, accent)

    totals_x = table_x + table_width - 170
    text(totals_x, row_y - 12, 9, "Subtotal")
    text(totals_x + 100, row_y - 12, 9, f"${context['subtotal']:.2f}")
    text(totals_x, row_y - 30, 9, "Tax (8%)")
    text(totals_x + 100, row_y - 30, 9, f"${context['tax']:.2f}")
    rectangle(totals_x - 8, row_y - 58, 178, 22, accent)
    text(totals_x, row_y - 51, 10, "TOTAL", bold=True, color=(1, 1, 1))
    text(totals_x + 92, row_y - 51, 10, f"${context['total']:.2f}", bold=True, color=(1, 1, 1))

    footer_y = 72
    text(content_x, footer_y + 34, 9, "PAYMENT DETAILS", bold=True, color=accent)
    text(content_x, footer_y + 18, 8, f"Reference: {invoice_number} | Method: bank transfer | {context['payment_terms']}")
    text(content_x, footer_y, 8, "Questions: billing@cedarstone.test | Thank you for your business.")
    text(content_x, 34, 7, f"SYNTHETIC RESEARCH FIXTURE | Template: {template_name}", color=(0.35, 0.35, 0.35))

    content = "\n".join(commands).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    payload = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{number} 0 obj\n".encode())
        payload.extend(obj)
        payload.extend(b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode())
    payload.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(payload)


def make_purchase_order_pdf(context: dict[str, Any], template_name: str) -> bytes:
    commands: list[str] = []

    def text(
        x: int,
        y: int,
        size: int,
        value: str,
        *,
        bold: bool = False,
        color: tuple[float, float, float] = (0, 0, 0),
    ) -> None:
        red, green, blue = color
        commands.extend(
            [
                "BT",
                f"{red:.3f} {green:.3f} {blue:.3f} rg",
                f"/{'F2' if bold else 'F1'} {size} Tf",
                f"1 0 0 1 {x} {y} Tm",
                f"({pdf_literal(value)}) Tj",
                "ET",
            ]
        )

    def rectangle(
        x: int,
        y: int,
        width: int,
        height: int,
        color: tuple[float, float, float],
        *,
        stroke: bool = False,
    ) -> None:
        red, green, blue = color
        commands.append(f"{red:.3f} {green:.3f} {blue:.3f} {'RG' if stroke else 'rg'}")
        commands.append(f"{x} {y} {width} {height} re {'S' if stroke else 'f'}")

    def line(x1: int, y1: int, x2: int, y2: int, color: tuple[float, float, float]) -> None:
        red, green, blue = color
        commands.extend([f"{red:.3f} {green:.3f} {blue:.3f} RG", f"{x1} {y1} m {x2} {y2} l S"])

    palette = {
        "Modern Procurement": (0.08, 0.25, 0.42),
        "Classic Purchase Form": (0.22, 0.22, 0.22),
        "Vendor Sidebar": (0.08, 0.44, 0.38),
        "Operations Grid": (0.74, 0.35, 0.10),
        "Executive Approval": (0.34, 0.22, 0.52),
    }
    accent = palette[template_name]
    po_number = context["purchase_order_number"]

    if template_name == "Modern Procurement":
        rectangle(0, 704, 612, 88, accent)
        text(40, 749, 22, "PURCHASE ORDER", bold=True, color=(1, 1, 1))
        text(40, 727, 10, context["buyer"], bold=True, color=(1, 1, 1))
        text(439, 749, 10, po_number, bold=True, color=(1, 1, 1))
        metadata_y = 680
        table_y = 526
        content_x = 40
    elif template_name == "Classic Purchase Form":
        rectangle(24, 24, 564, 744, accent, stroke=True)
        text(42, 735, 14, context["buyer"], bold=True)
        text(354, 731, 19, "PURCHASE ORDER", bold=True)
        line(42, 708, 570, 708, accent)
        text(450, 713, 8, po_number, bold=True)
        metadata_y = 680
        table_y = 518
        content_x = 42
    elif template_name == "Vendor Sidebar":
        rectangle(0, 0, 126, 792, accent)
        text(18, 746, 16, "PURCHASE", bold=True, color=(1, 1, 1))
        text(18, 726, 16, "ORDER", bold=True, color=(1, 1, 1))
        text(18, 696, 8, po_number, bold=True, color=(1, 1, 1))
        text(18, 658, 8, "BUYER", bold=True, color=(0.82, 1, 0.94))
        buyer_name, buyer_suffix = context["buyer"].rsplit(" ", 1)
        text(18, 642, 8, buyer_name, color=(1, 1, 1))
        text(18, 628, 8, buyer_suffix, color=(1, 1, 1))
        text(148, 744, 15, "PROCUREMENT REQUEST", bold=True, color=accent)
        metadata_y = 700
        table_y = 508
        content_x = 148
    elif template_name == "Operations Grid":
        rectangle(36, 720, 540, 48, (0.98, 0.92, 0.87))
        rectangle(36, 720, 12, 48, accent)
        text(60, 739, 18, "PURCHASE ORDER", bold=True, color=accent)
        text(435, 739, 10, po_number, bold=True)
        text(42, 694, 11, context["buyer"], bold=True)
        metadata_y = 666
        table_y = 510
        content_x = 42
    else:
        text(42, 746, 12, context["buyer"], bold=True)
        text(360, 738, 21, "PURCHASE ORDER", bold=True, color=accent)
        rectangle(42, 684, 528, 35, (0.94, 0.92, 0.97))
        text(52, 696, 10, f"{po_number}  |  {context['status']}  |  {context['department']}", bold=True)
        metadata_y = 656
        table_y = 500
        content_x = 42

    right_x = 386 if content_x < 100 else 394
    text(content_x, metadata_y, 9, "SUPPLIER", bold=True, color=accent)
    text(content_x, metadata_y - 16, 11, context["vendor"], bold=True)
    text(content_x, metadata_y - 31, 8, f"orders@{filename_slug(context['vendor']).lower()}.cedarstone.test")
    text(content_x, metadata_y - 45, 8, "480 Commerce Park, Toronto, Ontario")
    text(content_x, metadata_y - 67, 9, "DELIVER TO", bold=True, color=accent)
    text(content_x, metadata_y - 83, 9, context["ship_to"], bold=True)
    text(content_x, metadata_y - 98, 8, "Receiving desk, 100 Research Avenue")

    text(right_x, metadata_y, 9, "ORDER DETAILS", bold=True, color=accent)
    text(right_x, metadata_y - 16, 8, f"Issued: {context['record_date']}")
    text(right_x, metadata_y - 31, 8, f"Required: {context['required_date']}")
    text(right_x, metadata_y - 46, 8, f"Terms: {context['payment_terms']}")
    text(right_x, metadata_y - 61, 8, f"Shipping: {context['shipping_terms']}")
    text(right_x, metadata_y - 76, 8, f"Requester: {context['requested_by']}")
    text(right_x, metadata_y - 91, 8, f"Cost center: {context['cost_center']}")

    table_x = content_x
    table_width = 570 - table_x
    rectangle(table_x, table_y, table_width, 24, accent)
    text(table_x + 7, table_y + 8, 8, "ITEM", bold=True, color=(1, 1, 1))
    text(table_x + 70, table_y + 8, 8, "DESCRIPTION", bold=True, color=(1, 1, 1))
    text(table_x + table_width - 164, table_y + 8, 8, "QTY", bold=True, color=(1, 1, 1))
    text(table_x + table_width - 115, table_y + 8, 8, "UNIT", bold=True, color=(1, 1, 1))
    text(table_x + table_width - 57, table_y + 8, 8, "TOTAL", bold=True, color=(1, 1, 1))

    row_y = table_y - 20
    for index, item in enumerate(context["purchase_items"]):
        if index % 2:
            rectangle(table_x, row_y - 5, table_width, 18, (0.96, 0.96, 0.96))
        text(table_x + 7, row_y, 7, item["sku"])
        text(table_x + 70, row_y, 7, item["description"][:37])
        text(table_x + table_width - 158, row_y, 7, str(item["quantity"]))
        text(table_x + table_width - 119, row_y, 7, f"${item['unit_price']:.2f}")
        text(table_x + table_width - 62, row_y, 7, f"${item['line_total']:.2f}")
        row_y -= 20
    line(table_x, row_y + 8, table_x + table_width, row_y + 8, accent)

    totals_x = table_x + table_width - 184
    text(totals_x, row_y - 12, 8, "Subtotal")
    text(totals_x + 112, row_y - 12, 8, f"${context['subtotal']:.2f}")
    text(totals_x, row_y - 28, 8, "Shipping")
    text(totals_x + 112, row_y - 28, 8, f"${context['shipping']:.2f}")
    text(totals_x, row_y - 44, 8, "Tax (8%)")
    text(totals_x + 112, row_y - 44, 8, f"${context['tax']:.2f}")
    rectangle(totals_x - 8, row_y - 70, 192, 21, accent)
    text(totals_x, row_y - 63, 9, "ORDER TOTAL", bold=True, color=(1, 1, 1))
    text(totals_x + 104, row_y - 63, 9, f"${context['total']:.2f}", bold=True, color=(1, 1, 1))

    footer_x = content_x
    text(footer_x, 111, 8, "APPROVAL AND DELIVERY INSTRUCTIONS", bold=True, color=accent)
    text(footer_x, 95, 7, f"Approved by: {context['approved_by']} | Department: {context['department']} | Project: {context['project']}")
    text(footer_x, 80, 7, "Deliver during receiving hours, reference the PO number, and include a packing slip.")
    text(footer_x, 65, 7, "Changes require written buyer approval. Invoice quantities must not exceed this order.")
    text(footer_x, 34, 7, f"SYNTHETIC RESEARCH FIXTURE | Template: {template_name}", color=(0.35, 0.35, 0.35))

    content = "\n".join(commands).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    payload = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{number} 0 obj\n".encode())
        payload.extend(obj)
        payload.extend(b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    payload.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode())
    payload.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(payload)


def write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def file_manifest_record(owner: str, relative_path: str, payload_hash: str, license_id: str, **extra: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "entity_type": "file",
        "owner": owner,
        "path": relative_path,
        "sha256": payload_hash,
        "license": license_id,
        "generator_version": GENERATOR_VERSION,
    }
    record.update(extra)
    return record


def load_assets(
    media_dir: Path,
    asset_manifest: Path,
    allowed_licenses: set[str],
    output_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    data = json.loads(asset_manifest.read_text(encoding="utf-8"))
    entries = data.get("assets", [])
    by_path = {entry["path"]: entry for entry in entries}
    actual = {
        path.relative_to(media_dir).as_posix(): path
        for path in media_dir.rglob("*")
        if path.is_file()
        and path.relative_to(media_dir).parts[0] not in {"real_documents", "financial_documents"}
        and not any(part.startswith(".") for part in path.relative_to(media_dir).parts)
    }
    if set(actual) != set(by_path):
        missing_metadata = sorted(set(actual) - set(by_path))
        missing_files = sorted(set(by_path) - set(actual))
        raise ValueError(f"Asset manifest mismatch; missing metadata={missing_metadata}, missing files={missing_files}")

    records: list[dict[str, Any]] = []
    counts = {user: 0 for user in USERS}
    for relative_path in sorted(actual):
        entry = by_path[relative_path]
        owner, user_path = relative_path.split("/", 1)
        if owner not in USERS:
            raise ValueError(f"Unsupported media owner in {relative_path}")
        license_id = entry["license"]
        if license_id not in allowed_licenses:
            raise ValueError(f"Disallowed license {license_id} for {relative_path}")
        actual_hash = sha256_file(actual[relative_path])
        expected_hash = entry.get("sha256")
        if expected_hash and expected_hash != actual_hash:
            raise ValueError(f"SHA-256 mismatch for {relative_path}: {actual_hash}")
        records.append(
            file_manifest_record(
                owner,
                user_path,
                actual_hash,
                license_id,
                creator=entry["creator"],
                source_url=entry.get("source_url", ""),
                license_url=entry["license_url"],
                source="bundled-asset",
            )
        )
        destination = output_dir / "files" / owner / user_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(actual[relative_path], destination)
        counts[owner] += 1
    return records, counts


def load_real_documents(
    media_dir: Path,
    catalog_path: Path,
    allowed_licenses: set[str],
    output_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    if catalog.get("version") != 1:
        raise ValueError("Unsupported real-document catalog version")
    sources = catalog.get("sources", {})
    entries = catalog.get("documents", [])
    by_bundled_path = {entry["bundled_path"]: entry for entry in entries}
    real_root = media_dir / "real_documents"
    actual = {
        path.relative_to(media_dir).as_posix(): path
        for path in real_root.rglob("*")
        if path.is_file() and not any(part.startswith(".") for part in path.relative_to(real_root).parts)
    }
    if set(actual) != set(by_bundled_path):
        missing_metadata = sorted(set(actual) - set(by_bundled_path))
        missing_files = sorted(set(by_bundled_path) - set(actual))
        raise ValueError(
            f"Real-document catalog mismatch; missing metadata={missing_metadata}, missing files={missing_files}"
        )

    records: list[dict[str, Any]] = []
    counts = {user: 0 for user in USERS}
    destinations: set[tuple[str, str]] = set()
    for bundled_path in sorted(actual):
        entry = by_bundled_path[bundled_path]
        owner = entry["owner"]
        destination_path = entry["destination_path"]
        source = sources.get(entry["source"])
        if owner not in USERS or source is None:
            raise ValueError(f"Invalid real-document ownership/source for {bundled_path}")
        destination_key = (owner, destination_path)
        if destination_key in destinations:
            raise ValueError(f"Duplicate real-document destination: {destination_key}")
        destinations.add(destination_key)
        license_id = source["license"]
        if license_id not in allowed_licenses:
            raise ValueError(f"Disallowed real-document license {license_id} for {bundled_path}")
        actual_hash = sha256_file(actual[bundled_path])
        if not entry.get("sha256") or entry["sha256"] != actual_hash:
            raise ValueError(f"SHA-256 mismatch for real document {bundled_path}: {actual_hash}")
        source_path = entry["source_path"]
        source_url = source["browser_base_url"].rstrip("/") + "/" + source_path
        records.append(
            file_manifest_record(
                owner,
                destination_path,
                actual_hash,
                license_id,
                creator=source["creator"],
                source_url=source_url,
                license_url=source["license_url"],
                source="retained-open-document",
                source_repository=source["repository_url"],
                source_revision=source["revision"],
                source_path=source_path,
            )
        )
        destination = output_dir / "files" / owner / destination_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(actual[bundled_path], destination)
        counts[owner] += 1
    return records, counts


def xlsx_column_index(reference: str) -> int:
    letters = "".join(character for character in reference if character.isalpha())
    result = 0
    for character in letters:
        result = result * 26 + ord(character.upper()) - ord("A") + 1
    return result - 1


def iter_xlsx_rows(path: Path, width: int) -> Iterable[list[str]]:
    spreadsheet_namespace = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    with zipfile.ZipFile(path) as archive:
        shared_root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
        shared_strings = [
            "".join(node.text or "" for node in item.iter(f"{spreadsheet_namespace}t"))
            for item in shared_root.findall(f"{spreadsheet_namespace}si")
        ]
        with archive.open("xl/worksheets/sheet1.xml") as worksheet:
            for _, row in ElementTree.iterparse(worksheet, events=("end",)):
                if row.tag != f"{spreadsheet_namespace}row":
                    continue
                values = [""] * width
                for cell in row.findall(f"{spreadsheet_namespace}c"):
                    index = xlsx_column_index(cell.get("r", "A1"))
                    raw_value = cell.findtext(f"{spreadsheet_namespace}v") or ""
                    if 0 <= index < width:
                        if cell.get("t") == "s":
                            values[index] = shared_strings[int(raw_value)]
                        elif cell.get("t") == "inlineStr":
                            values[index] = "".join(
                                node.text or "" for node in cell.iter(f"{spreadsheet_namespace}t")
                            )
                        else:
                            values[index] = raw_value
                row.clear()
                yield values


def excel_datetime_text(value: str) -> str:
    if not value or value.upper() == "NA":
        return "Not recorded"
    parsed = datetime(1899, 12, 30) + timedelta(days=float(value))
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def load_selected_order_rows(path: Path, selected_order_ids: set[str]) -> dict[str, list[list[str]]]:
    expected_header = ["rec_id", "order_id", "order_date", "shipped_at", "prod_sku", "prod_qty"]
    selected = {order_id: [] for order_id in selected_order_ids}
    for index, row in enumerate(iter_xlsx_rows(path, len(expected_header))):
        if index == 0:
            if row != expected_header:
                raise ValueError(f"Unexpected e-commerce order workbook header: {row}")
            continue
        if row[1] in selected:
            selected[row[1]].append(row)
    missing = sorted(order_id for order_id, rows in selected.items() if not rows)
    if missing:
        raise ValueError(f"Selected customer orders are missing from the source workbook: {missing}")
    return selected


def load_additional_order_rows(
    path: Path,
    excluded_order_ids: set[str],
    count: int,
) -> list[tuple[str, list[list[str]]]]:
    expected_header = ["rec_id", "order_id", "order_date", "shipped_at", "prod_sku", "prod_qty"]
    selected: dict[str, list[list[str]]] = {}
    for index, row in enumerate(iter_xlsx_rows(path, len(expected_header))):
        if index == 0:
            if row != expected_header:
                raise ValueError(f"Unexpected e-commerce order workbook header: {row}")
            continue
        order_id = row[1]
        if order_id in excluded_order_ids:
            continue
        if order_id not in selected and len(selected) < count:
            selected[order_id] = []
        if order_id in selected:
            selected[order_id].append(row)
    if len(selected) != count or any(not rows for rows in selected.values()):
        raise ValueError(f"Could not select {count} additional customer orders from the source workbook")
    return list(selected.items())


def make_order_plot_svg(title: str, source_rows: list[list[str]], source_label: str) -> bytes:
    quantities: dict[str, int] = {}
    for row in source_rows:
        sku = row[4] or "UNKNOWN-SKU"
        quantities[sku] = quantities.get(sku, 0) + max(1, int(float(row[5] or 1)))
    bars = sorted(quantities.items(), key=lambda item: (-item[1], item[0]))[:10]
    maximum = max(quantity for _, quantity in bars)
    chart_width = 660
    bar_height = 28
    elements = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="520" viewBox="0 0 900 520">',
        '<rect width="900" height="520" fill="#f8fafc"/>',
        f'<text x="42" y="48" font-family="sans-serif" font-size="24" font-weight="700" fill="#172554">{xml_escape(title)}</text>',
        f'<text x="42" y="74" font-family="sans-serif" font-size="12" fill="#475569">{xml_escape(source_label)}</text>',
    ]
    for index, (sku, quantity) in enumerate(bars):
        y = 104 + index * 38
        width = max(12, round(chart_width * quantity / maximum))
        color = ("#2563eb", "#0891b2", "#059669", "#65a30d", "#ca8a04")[index % 5]
        elements.extend(
            [
                f'<text x="42" y="{y + 19}" font-family="monospace" font-size="12" fill="#334155">{xml_escape(sku[:24])}</text>',
                f'<rect x="232" y="{y}" width="{width}" height="{bar_height}" rx="4" fill="{color}"/>',
                f'<text x="{min(870, 242 + width)}" y="{y + 19}" font-family="sans-serif" font-size="12" fill="#0f172a">{quantity}</text>',
            ]
        )
    elements.extend(
        [
            '<text x="42" y="494" font-family="sans-serif" font-size="11" fill="#64748b">Quantity by product SKU; derived from pinned CC BY 4.0 order rows.</text>',
            "</svg>",
            "",
        ]
    )
    return "\n".join(elements).encode()


def load_financial_documents(
    spec: dict[str, Any],
    media_dir: Path,
    catalog_path: Path,
    allowed_licenses: set[str],
    output_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    if catalog.get("version") != 2:
        raise ValueError("Unsupported financial-document catalog version")
    sources = catalog.get("sources", {})
    order_source = sources.get("ecommerce-orders")
    if not order_source:
        raise ValueError("Financial-document catalog is missing required sources")
    if order_source["license"] not in allowed_licenses:
        raise ValueError(f"Disallowed financial-document license: {order_source['license']}")

    order_dataset = catalog.get("order_dataset", {})
    expected_files = {order_dataset["bundled_path"]: order_dataset["sha256"]}
    financial_root = media_dir / "financial_documents"
    actual_files = {
        path.relative_to(media_dir).as_posix(): path
        for path in financial_root.rglob("*")
        if path.is_file() and not any(part.startswith(".") for part in path.relative_to(financial_root).parts)
    }
    if set(actual_files) != set(expected_files):
        raise ValueError(
            "Financial-document catalog mismatch; "
            f"missing metadata={sorted(set(actual_files) - set(expected_files))}, "
            f"missing files={sorted(set(expected_files) - set(actual_files))}"
        )
    for bundled_path, expected_hash in expected_files.items():
        if sha256_file(actual_files[bundled_path]) != expected_hash:
            raise ValueError(f"SHA-256 mismatch for financial source {bundled_path}")

    records: list[dict[str, Any]] = []
    counts = {user: 0 for user in USERS}
    destinations: set[tuple[str, str]] = set()

    def add_file(
        owner: str,
        relative_path: str,
        payload: bytes,
        source: dict[str, Any],
        source_kind: str,
        **extra: Any,
    ) -> None:
        key = (owner, relative_path)
        if owner not in USERS or key in destinations:
            raise ValueError(f"Invalid or duplicate financial-document destination: {key}")
        destinations.add(key)
        write_bytes(output_dir / "files" / owner / relative_path, payload)
        records.append(
            file_manifest_record(
                owner,
                relative_path,
                sha256_bytes(payload),
                source["license"],
                creator=source["creator"],
                source=source_kind,
                source_dataset=source["title"],
                source_url=source["source_url"],
                source_doi=source["doi"],
                source_revision=source["revision"],
                license_url=source["license_url"],
                synthetic=False,
                **extra,
            )
        )
        counts[owner] += 1

    order_workbook = actual_files[order_dataset["bundled_path"]]
    workbook_payload = order_workbook.read_bytes()
    for owner in USERS:
        add_file(
            owner,
            order_dataset["destination_path"],
            workbook_payload,
            order_source,
            "open-dataset-source",
            source_path="E-Commerce DataSet.xlsx",
        )

    order_entries = catalog.get("order_records", [])
    order_rows = load_selected_order_rows(order_workbook, {entry["order_id"] for entry in order_entries})
    for entry in order_entries:
        source_rows = order_rows[entry["order_id"]]
        if len(source_rows) != int(entry["line_count"]):
            raise ValueError(f"Customer order line-count mismatch for {entry['order_id']}")
        rendered_rows = [
            [row[0], row[1], excel_datetime_text(row[2]), excel_datetime_text(row[3]), row[4], row[5]]
            for row in source_rows
        ]
        payload = make_xlsx(
            f"Customer order {entry['order_id']}",
            "Authentic customer-order record selected from the CC BY 4.0 E-Commerce Dataset.",
            ["Record ID", "Order ID", "Order date", "Shipped at", "Product SKU", "Quantity"],
            rendered_rows,
            {
                "Dataset DOI": order_source["doi"],
                "Source version": order_source["revision"],
                "Line records": str(len(rendered_rows)),
                "Transformation": "Selected source rows reformatted as an individual workbook",
            },
        )
        add_file(
            entry["owner"],
            entry["document_destination_path"],
            payload,
            order_source,
            "derived-open-dataset-document",
            source_path="E-Commerce DataSet.xlsx",
            source_record_id=entry["order_id"],
            source_record_sha256=order_dataset["sha256"],
            source_line_count=len(rendered_rows),
            transformation="Selected authentic order rows reformatted into an individual XLSX workbook",
        )

    derivative_targets = {
        key: int(value) for key, value in spec["open_dataset_derivatives_per_user"].items()
    }
    if derivative_targets != {"orders": 160, "invoices": 120, "plots": 157}:
        raise ValueError(f"Unexpected open-dataset derivative targets: {derivative_targets}")
    additional_orders = load_additional_order_rows(
        order_workbook,
        {entry["order_id"] for entry in order_entries},
        derivative_targets["orders"] * len(USERS),
    )
    allocated_orders = {
        owner: additional_orders[user_index :: len(USERS)][: derivative_targets["orders"]]
        for user_index, owner in enumerate(USERS)
    }
    for user_index, owner in enumerate(USERS):
        owner_orders = allocated_orders[owner]
        order_document_ids: list[str] = []
        for index, (source_order_id, source_rows) in enumerate(owner_orders, start=1):
            order_document_id = f"DATA-ORDER-{user_index + 1}-{index:04d}"
            order_document_ids.append(order_document_id)
            rendered_rows = [
                [row[0], row[1], excel_datetime_text(row[2]), excel_datetime_text(row[3]), row[4], row[5]]
                for row in source_rows
            ]
            order_payload = make_xlsx(
                f"Dataset customer order {source_order_id}",
                "Order Record",
                ["Record ID", "Order ID", "Order date", "Shipped at", "Product SKU", "Quantity"],
                rendered_rows,
                {
                    "Document ID": order_document_id,
                    "Dataset DOI": order_source["doi"],
                    "Source version": order_source["revision"],
                    "Transformation": "Selected source rows reformatted as a working order workbook",
                },
            )
            order_path = f"Sales/Orders/Dataset_Order_{user_index + 1}_{index:04d}.xlsx"
            add_file(
                owner,
                order_path,
                order_payload,
                order_source,
                "derived-open-dataset-order",
                document_id=order_document_id,
                document_type="Dataset Customer Order",
                source_path="E-Commerce DataSet.xlsx",
                source_record_id=source_order_id,
                source_record_sha256=order_dataset["sha256"],
                source_line_count=len(rendered_rows),
                transformation="Selected authentic order rows reformatted into an individual XLSX workbook",
            )

            if index <= derivative_targets["invoices"]:
                invoice_id = f"DATA-INV-{user_index + 1}-{index:04d}"
                line_items = []
                for row in source_rows[:6]:
                    quantity = max(1, int(float(row[5] or 1)))
                    unit_price = 25 + sum(ord(character) for character in row[4]) % 475
                    line_items.append(
                        {
                            "sku": row[4],
                            "description": f"Dataset product {row[4]}",
                            "quantity": quantity,
                            "unit_price": unit_price,
                            "line_total": quantity * unit_price,
                        }
                    )
                subtotal = sum(item["line_total"] for item in line_items)
                tax = round(subtotal * 0.08, 2)
                issued_text = excel_datetime_text(source_rows[0][2])
                issued_date = issued_text[:10] if issued_text != "Not recorded" else spec["calendar_anchor"]
                due_date = (date.fromisoformat(issued_date) + timedelta(days=30)).isoformat()
                customer = CUSTOMERS[(index + user_index * 3) % len(CUSTOMERS)]
                invoice_context = {
                    "invoice_number": invoice_id,
                    "seller": COMPANY_NAME,
                    "customer": customer,
                    "invoice_status": ("Paid", "Open", "Approved")[(index + user_index) % 3],
                    "record_date": issued_date,
                    "due_date": due_date,
                    "payment_terms": "Net 30",
                    "line_items": line_items,
                    "subtotal": subtotal,
                    "tax": tax,
                    "total": subtotal + tax,
                }
                template_name = INVOICE_TEMPLATES[(index + user_index) % len(INVOICE_TEMPLATES)]
                invoice_payload = make_invoice_pdf(invoice_context, template_name)
                invoice_path = f"Finance/Invoices/Dataset_Invoice_{user_index + 1}_{index:04d}_{filename_slug(customer)}.pdf"
                add_file(
                    owner,
                    invoice_path,
                    invoice_payload,
                    order_source,
                    "derived-open-dataset-invoice",
                    document_id=invoice_id,
                    document_type="Dataset-derived Invoice",
                    subject=customer,
                    related_order_document_id=order_document_id,
                    related_order_path=order_path,
                    source_path="E-Commerce DataSet.xlsx",
                    source_record_id=source_order_id,
                    source_record_sha256=order_dataset["sha256"],
                    source_line_count=len(source_rows),
                    invoice_template=template_name,
                    synthetic_enrichment=True,
                    transformation="Authentic order quantities converted to a synthetic-priced invoice; customer and prices are generated",
                )

        for plot_index in range(derivative_targets["plots"]):
            related_indexes = [(plot_index + offset * 17) % len(owner_orders) for offset in range(8)]
            related_orders = [owner_orders[index] for index in related_indexes]
            plot_rows = [row for _, rows in related_orders for row in rows]
            related_document_ids = [order_document_ids[index] for index in related_indexes]
            plot_id = f"ORDER-PLOT-{user_index + 1}-{plot_index + 1:04d}"
            plot_payload = make_order_plot_svg(
                f"Order quantity profile {plot_index + 1:03d}",
                plot_rows,
                f"Eight-order window | Dataset DOI {order_source['doi']}",
            )
            plot_path = f"Analytics/Order Plots/Order_Quantity_Plot_{user_index + 1}_{plot_index + 1:04d}.svg"
            add_file(
                owner,
                plot_path,
                plot_payload,
                order_source,
                "derived-open-dataset-plot",
                document_id=plot_id,
                document_type="Order Quantity Plot",
                related_order_document_ids=related_document_ids,
                source_path="E-Commerce DataSet.xlsx",
                source_record_ids=[order_id for order_id, _ in related_orders],
                source_record_sha256=order_dataset["sha256"],
                source_line_count=len(plot_rows),
                plot_kind="sku-quantity-bar",
                transformation="Authentic order quantities aggregated into an SVG bar chart",
            )
    return records, counts


def generate_documents(output_dir: Path, records: list[dict[str, Any]], counts: dict[str, int]) -> None:
    for filename, (title, body) in GENERATED_DOCUMENTS.items():
        relative_path = f"documents/{filename}"
        if filename.endswith(".docx"):
            payload = make_docx(title, body)
        elif filename.endswith(".pdf"):
            payload = make_pdf(title, body)
        else:
            raise ValueError(f"Unsupported generated document: {filename}")
        write_bytes(output_dir / "files" / "maya.patel" / relative_path, payload)
        records.append(
            file_manifest_record(
                "maya.patel",
                relative_path,
                sha256_bytes(payload),
                "CC-BY-4.0",
                creator=DATASET_CREATOR,
                source="generated",
                license_url=DATASET_LICENSE_URL,
            )
        )
        counts["maya.patel"] += 1


def format_cycle(weights: dict[str, int]) -> list[str]:
    normalized = {extension: int(weight) for extension, weight in weights.items()}
    total = sum(normalized.values())
    if total != 100:
        raise ValueError("file_format_weights must sum to 100")

    # Smooth weighted round-robin keeps every supported format represented even
    # when linked business records leave fewer than 100 generic files to fill.
    # Across the complete cycle it still produces the exact configured weights.
    extensions = list(normalized)
    extension_order = {extension: index for index, extension in enumerate(extensions)}
    current = {extension: 0 for extension in extensions}
    cycle: list[str] = []
    for _ in range(total):
        for extension in extensions:
            current[extension] += normalized[extension]
        selected = max(extensions, key=lambda extension: (current[extension], -extension_order[extension]))
        current[selected] -= total
        cycle.append(selected)
    return cycle


def filename_slug(value: str) -> str:
    return "_".join("".join(character for character in part if character.isalnum()) for part in value.split())


def build_business_context(
    profile: dict[str, str],
    owner: str,
    user_index: int,
    index: int,
    record_date: date,
    seed: int,
) -> dict[str, Any]:
    rng = random.Random(seed + user_index * 100_003 + index * 97)
    customer = CUSTOMERS[(index * 3 + index // 7 + user_index) % len(CUSTOMERS)]
    vendor = VENDORS[(index * 5 + index // 3 + user_index) % len(VENDORS)]
    project = PROJECTS[(index * 7 + index // 5 + user_index) % len(PROJECTS)]
    team = TEAMS[(index * 11 + index // 4 + user_index) % len(TEAMS)]
    kind = profile["kind"]
    if kind in {"transaction", "customer"}:
        subject = vendor if profile["area"] == "Procurement" else customer
    elif kind == "vendor":
        subject = vendor
    elif kind == "project":
        subject = project
    elif kind in {"meeting", "people", "operations", "report"}:
        subject = team
    else:
        subject = f"Distribution Center {(index % 4) + 1}"
    if kind == "inventory":
        subject = f"Distribution Center {(index % 4) + 1}"

    identifier = f"{profile['prefix']}-{record_date.year}-{index + 1:05d}"
    statuses = ("Approved", "In Review", "Open", "Scheduled", "Completed")
    line_items = []
    for item_index in range(8):
        product, base_price = PRODUCTS[(index + item_index * 3 + user_index) % len(PRODUCTS)]
        quantity = 1 + ((index + item_index * 2) % 6)
        unit_price = base_price + rng.randrange(0, 85)
        line_items.append(
            {
                "sku": f"SKU-{(index * 13 + item_index * 17) % 9000 + 1000}",
                "description": product,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": quantity * unit_price,
            }
        )
    subtotal = sum(item["line_total"] for item in line_items)
    tax = round(subtotal * 0.08)
    metrics = []
    metric_names = (
        "Revenue attainment", "On-time delivery", "Customer satisfaction", "Open work items",
        "Forecast accuracy", "Quality pass rate", "Response SLA", "Budget utilization",
    )
    for metric_index, metric_name in enumerate(metric_names):
        current = 62 + ((index * 7 + metric_index * 9 + user_index) % 38)
        target = min(100, current + 3 + metric_index % 5)
        metrics.append({"metric": metric_name, "current": current, "target": target, "variance": current - target})
    action_items = []
    for action_index in range(8):
        action_items.append(
            {
                "action": (
                    "Confirm scope", "Validate source data", "Review customer feedback", "Update delivery plan",
                    "Resolve open dependency", "Publish revised forecast", "Complete quality review", "Share stakeholder update",
                )[action_index],
                "owner": BUSINESS_NAMES[(index + action_index + user_index) % len(BUSINESS_NAMES)],
                "due_date": (record_date + timedelta(days=3 + action_index * 2)).isoformat(),
                "status": ("Open", "In Progress", "Scheduled", "Blocked")[(index + action_index) % 4],
            }
        )
    return {
        "document_id": identifier,
        "title": f"{profile['label']} - {identifier}",
        "owner": owner,
        "area": profile["area"],
        "category": profile["category"],
        "kind": kind,
        "subject": subject,
        "customer": customer,
        "vendor": vendor,
        "project": project,
        "team": team,
        "record_date": record_date.isoformat(),
        "due_date": (record_date + timedelta(days=30)).isoformat(),
        "quarter": f"Q{(record_date.month - 1) // 3 + 1}",
        "status": statuses[(index + user_index) % len(statuses)],
        "prepared_by": BUSINESS_NAMES[(index + user_index * 4) % len(BUSINESS_NAMES)],
        "approved_by": BUSINESS_NAMES[(index + user_index * 4 + 3) % len(BUSINESS_NAMES)],
        "attendees": [BUSINESS_NAMES[(index + offset + user_index) % len(BUSINESS_NAMES)] for offset in range(6)],
        "line_items": line_items,
        "subtotal": subtotal,
        "tax": tax,
        "total": subtotal + tax,
        "metrics": metrics,
        "action_items": action_items,
    }


def business_sections(context: dict[str, Any]) -> list[tuple[str, list[str]]]:
    details = [
        f"Document ID: {context['document_id']}",
        f"Business area: {context['area']} / {context['category']}",
        f"Prepared by: {context['prepared_by']} ({context['owner']})",
        f"Record date: {context['record_date']}",
        f"Status: {context['status']}",
        f"Subject: {context['subject']}",
        "Data classification: synthetic business fixture for open research",
    ]
    kind = context["kind"]
    if kind == "transaction":
        item_lines = [
            f"{item['sku']} | {item['description']} | qty {item['quantity']} x ${item['unit_price']:.2f} = ${item['line_total']:.2f}"
            for item in context["line_items"]
        ]
        return [
            ("Document Details", details),
            ("Customer and Supplier", [f"Customer: {context['customer']}", f"Supplier: {context['vendor']}", f"Payment due: {context['due_date']}"]),
            ("Line Items", item_lines),
            ("Totals", [f"Subtotal: ${context['subtotal']:.2f}", f"Tax: ${context['tax']:.2f}", f"Total: ${context['total']:.2f}"]),
            ("Approval and Terms", [f"Approved by: {context['approved_by']}", "Payment terms: net 30 days", "Disputes should be raised within ten business days."]),
        ]
    if kind == "meeting":
        return [
            ("Meeting Details", details + [f"Attendees: {', '.join(context['attendees'])}"]),
            ("Agenda", ["Review prior commitments and current operating metrics.", "Discuss delivery risks and customer-impacting decisions.", "Agree owners and due dates for the next work period."]),
            ("Discussion Notes", [f"The {context['team']} team reviewed progress for {context['project']}.", "The group confirmed that the current scope remains achievable.", "Dependencies on customer feedback and source-data validation remain the main risks.", "Budget and staffing remain within the approved operating range."]),
            ("Decisions", ["Keep the current milestone sequence.", "Escalate unresolved data-quality issues within one business day.", "Publish a written stakeholder update after the quality review."]),
            ("Action Items", [f"{item['action']} — {item['owner']} — due {item['due_date']} — {item['status']}" for item in context["action_items"]]),
        ]
    if kind == "project":
        return [
            ("Project Overview", details + [f"Project: {context['project']}", f"Delivery team: {context['team']}"]),
            ("Objective", [f"Deliver the next approved phase of {context['project']} with measurable improvements to reliability, usability, and reporting.", "The scope includes discovery, configuration, validation, enablement, and transition to operations."]),
            ("Milestone Status", ["Discovery and stakeholder interviews: complete", "Solution design and acceptance criteria: complete", "Configuration and integration: in progress", "User validation and training: scheduled", "Production transition: pending final approval"]),
            ("Risks and Mitigations", ["Source-data inconsistencies — run validation before migration.", "Limited reviewer availability — reserve review sessions two weeks ahead.", "Late scope additions — route changes through the documented approval process."]),
            ("Next Actions", [f"{item['action']} — owner {item['owner']} — due {item['due_date']}" for item in context["action_items"]]),
        ]
    if kind == "inventory":
        return [
            ("Inventory Record", details + [f"Location: {context['subject']}", f"Carrier: {context['vendor']}"]),
            ("Movement Summary", [f"Eight tracked service items with a recorded value of ${context['subtotal']:.2f}.", "All received quantities were compared with the expected manifest.", "Two low-stock items require replenishment during the next ordering cycle."]),
            ("Tracked Items", [f"{item['sku']} | {item['description']} | on hand {item['quantity'] * 8} | reorder at {item['quantity'] * 4}" for item in context["line_items"]]),
            ("Exceptions", ["One carton arrived with minor exterior damage; contents passed inspection.", "No quantity discrepancies were found.", "Serial and batch references were recorded in the inventory register."]),
            ("Next Steps", ["Release accepted items to available stock.", "Create replenishment requests for low-stock items.", "Attach carrier confirmation to the monthly operations report."]),
        ]
    if kind == "report":
        return [
            ("Report Context", details + [f"Reporting period: {context['quarter']} {context['record_date'][:4]}", f"Team: {context['team']}"]),
            ("Executive Summary", [f"The {context['team']} portfolio remained stable during the reporting period.", "Delivery performance improved, while forecast accuracy and response SLA require focused follow-up.", "No issue currently threatens the approved quarterly objectives."]),
            ("Key Performance Indicators", [f"{metric['metric']}: {metric['current']}% against {metric['target']}% target (variance {metric['variance']} points)" for metric in context["metrics"]]),
            ("Analysis", ["Customer satisfaction remained resilient despite higher request volume.", "The largest delivery variance came from late source-data confirmation.", "Budget utilization is consistent with the approved forecast.", "Quality pass rates improved after adding a pre-release checklist."]),
            ("Recommendations", ["Prioritize source-data validation before scheduling delivery.", "Review SLA capacity at the weekly operations meeting.", "Continue the pre-release quality checklist.", "Reforecast open work at the midpoint of the next period."]),
        ]
    if kind == "people":
        return [
            ("People Record", details + [f"Team: {context['team']}", f"Coordinator: {context['prepared_by']}"]),
            ("Purpose", ["Document the participants, planned work, feedback, and follow-up commitments for this people-operations activity.", "The activity supports consistent onboarding, development, and workload planning."]),
            ("Participants", [f"{name} — {TEAMS[(index + len(name)) % len(TEAMS)]}" for index, name in enumerate(context["attendees"])]),
            ("Assessment", ["Preparation and participation met expectations.", "Examples demonstrated clear written communication and structured problem solving.", "Additional practice is recommended for prioritization under competing deadlines."]),
            ("Follow-up Actions", [f"{item['action']} — {item['owner']} — {item['due_date']}" for item in context["action_items"][:6]]),
        ]
    if kind == "vendor":
        return [
            ("Vendor Record", details + [f"Vendor: {context['vendor']}", f"Review owner: {context['prepared_by']}"]),
            ("Service Scope", ["Scheduled operational support and fulfillment services.", "Monthly reporting, exception handling, and quarterly service review.", "Standard response window of one business day."]),
            ("Performance Review", [f"{metric['metric']}: {metric['current']}%" for metric in context["metrics"][:6]]),
            ("Risks", ["Capacity during quarter-end processing requires advance confirmation.", "Two reporting fields need consistent definitions across systems.", "Renewal pricing should be confirmed before the next planning cycle."]),
            ("Actions", [f"{item['action']} — {item['owner']} — due {item['due_date']}" for item in context["action_items"][:6]]),
        ]
    if kind == "customer":
        return [
            ("Account Overview", details + [f"Customer: {context['customer']}", f"Account owner: {context['prepared_by']}"]),
            ("Business Context", [f"{context['customer']} is preparing the next phase of its operational reporting program.", "The customer values predictable delivery, clear documentation, and measurable adoption outcomes."]),
            ("Current Priorities", ["Improve visibility into order and service performance.", "Reduce manual reconciliation in monthly reporting.", "Train account administrators on repeatable quality checks.", "Agree a phased roadmap for the next quarter."]),
            ("Opportunity Summary", [f"Estimated program value: ${context['total']:.2f}", f"Related initiative: {context['project']}", "Commercial stage: solution review", "Decision window: within 30 days"]),
            ("Next Steps", [f"{item['action']} — {item['owner']} — {item['due_date']}" for item in context["action_items"][:6]]),
        ]
    return [
        ("Operations Record", details),
        ("Shift Summary", [f"The {context['team']} team completed the planned operating cycle.", "Incoming work was triaged, scheduled, and assigned before the handoff.", "No critical service interruption occurred during the period."]),
        ("Completed Work", ["Validated scheduled jobs and source files.", "Reviewed open exceptions and customer-impacting work.", "Updated the capacity plan and delivery board.", "Completed the documented quality checklist."]),
        ("Exceptions", ["One delayed source file was moved to the next processing window.", "A minor dashboard discrepancy was corrected before publication.", "No safety, security, or privacy incident was reported."]),
        ("Handoff", [f"{item['action']} — {item['owner']} — due {item['due_date']}" for item in context["action_items"][:6]]),
    ]


def business_table(context: dict[str, Any]) -> tuple[list[str], list[list[str | int | float]]]:
    kind = context["kind"]
    if kind == "transaction":
        columns = ["Item ID", "Description", "Quantity", "Unit Price", "Line Total", "Status"]
        rows = [[item["sku"], item["description"], item["quantity"], item["unit_price"], item["line_total"], context["status"]] for item in context["line_items"]]
    elif kind == "inventory":
        columns = ["SKU", "Item", "On Hand", "Reorder Point", "Inbound", "Stock Status"]
        rows = [[item["sku"], item["description"], item["quantity"] * 8, item["quantity"] * 4, item["quantity"] * 2, "Reorder" if item["quantity"] < 3 else "Available"] for item in context["line_items"]]
    elif kind == "report":
        columns = ["Metric", "Current Percent", "Target Percent", "Variance", "Owner", "Review Status"]
        rows = [[metric["metric"], metric["current"], metric["target"], metric["variance"], context["attendees"][index % 6], "Reviewed"] for index, metric in enumerate(context["metrics"])]
    elif kind in {"meeting", "project"}:
        columns = ["Action", "Owner", "Due Date", "Status", "Project", "Team"]
        rows = [[item["action"], item["owner"], item["due_date"], item["status"], context["project"], context["team"]] for item in context["action_items"]]
    elif kind == "people":
        columns = ["Participant", "Team", "Regular Hours", "Project Hours", "Total Hours", "Approval"]
        rows = [[name, TEAMS[(index + 2) % len(TEAMS)], 32 + index % 5, 4 + (index * 3) % 8, 40 + index % 4, "Approved"] for index, name in enumerate((*context["attendees"], *context["attendees"][:2]))]
    else:
        columns = ["Work Item", "Owner", "Due Date", "Status", "Business Area", "Subject"]
        rows = [[item["action"], item["owner"], item["due_date"], item["status"], context["area"], context["subject"]] for item in context["action_items"]]
    return columns, rows


def render_plain_sections(sections: list[tuple[str, list[str]]]) -> str:
    return "\n\n".join(f"{heading.upper()}\n" + "\n".join(lines) for heading, lines in sections)


def business_file_payload(extension: str, profile: dict[str, str], context: dict[str, Any]) -> bytes:
    title = context["title"]
    sections = business_sections(context)
    columns, rows = business_table(context)
    if extension == "txt":
        return f"{title}\n{'=' * len(title)}\n\n{render_plain_sections(sections)}\n".encode()
    if extension == "md":
        markdown = [f"# {title}"]
        for heading, lines in sections:
            markdown.extend(["", f"## {heading}", "", *[f"- {line}" for line in lines]])
        return ("\n".join(markdown) + "\n").encode()
    if extension == "csv":
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(columns)
        writer.writerows(rows)
        return stream.getvalue().encode()
    if extension == "json":
        return (
            json.dumps(
                {
                    "document": {
                        "id": context["document_id"], "title": title, "owner": context["owner"],
                        "date": context["record_date"], "status": context["status"], "subject": context["subject"],
                        "business_area": context["area"], "category": context["category"], "synthetic": True,
                    },
                    "details": {heading: lines for heading, lines in sections},
                    "records": [dict(zip(columns, row)) for row in rows],
                },
                sort_keys=True,
                indent=2,
            )
            + "\n"
        ).encode()
    body = render_plain_sections(sections)
    if extension == "pdf":
        return make_pdf(title, body)
    if extension == "docx":
        return make_docx(title, body)
    if extension == "xlsx":
        return make_xlsx(
            title,
            profile["label"],
            columns,
            rows,
            {
                "Document ID": context["document_id"],
                "Prepared by": context["prepared_by"],
                "Record date": context["record_date"],
                "Subject": context["subject"],
                "Status": context["status"],
            },
        )
    if extension == "pptx":
        slides = [
            ("Overview", [title, f"Subject: {context['subject']}", f"Prepared by: {context['prepared_by']}", f"Period: {context['quarter']} {context['record_date'][:4]}"]),
            *[(heading, lines[:7]) for heading, lines in sections[1:5]],
        ]
        return make_pptx(title, slides)
    raise ValueError(f"Unsupported extension: {extension}")


def generate_synthetic_invoices(
    spec: dict[str, Any],
    output_dir: Path,
    records: list[dict[str, Any]],
    counts: dict[str, int],
) -> None:
    profile = {
        "area": "Finance",
        "category": "Invoices",
        "kind": "transaction",
        "label": "Customer Invoice",
        "prefix": "INV",
    }
    anchor = date.fromisoformat(spec["calendar_anchor"])
    seed = int(spec["random_seed"])
    payment_terms = ("Net 15", "Net 30", "Due on receipt", "Net 45", "50% deposit / Net 15")
    invoice_statuses = ("Sent", "Paid", "Due", "Overdue", "Awaiting approval")

    for user_index, owner in enumerate(USERS):
        for index in range(40):
            record_date = anchor - timedelta(days=index * 11 + user_index * 3)
            context = build_business_context(profile, owner, user_index, index + 10_000, record_date, seed)
            template_name = INVOICE_TEMPLATES[(index + user_index) % len(INVOICE_TEMPLATES)]
            invoice_number = f"INV-{user_index + 1}-{index + 1:04d}"
            context.update(
                {
                    "invoice_number": invoice_number,
                    "seller": VENDORS[(index + user_index * 3) % len(VENDORS)],
                    "payment_terms": payment_terms[(index + user_index) % len(payment_terms)],
                    "invoice_status": invoice_statuses[(index * 2 + user_index) % len(invoice_statuses)],
                }
            )
            filename = f"Invoice_{invoice_number}_{filename_slug(context['customer'])}.pdf"
            relative_path = f"Finance/Invoices/{filename}"
            payload = make_invoice_pdf(context, template_name)
            write_bytes(output_dir / "files" / owner / relative_path, payload)
            records.append(
                file_manifest_record(
                    owner,
                    relative_path,
                    sha256_bytes(payload),
                    spec["dataset_license"],
                    creator=DATASET_CREATOR,
                    source="generated",
                    license_url=DATASET_LICENSE_URL,
                    document_id=invoice_number,
                    document_type="Customer Invoice",
                    subject=context["customer"],
                    invoice_template=template_name,
                    synthetic=True,
                )
            )
            counts[owner] += 1

        for index in range(16):
            record_date = anchor - timedelta(days=index * 19 + user_index * 7 + 5)
            context = build_business_context(profile, owner, user_index, index + 20_000, record_date, seed)
            invoice_number = f"INV-{user_index + 1}-G{index + 1:03d}"
            context["document_id"] = invoice_number
            context["title"] = f"Customer Invoice - {invoice_number}"
            filename = f"Customer_Invoice_{invoice_number}_{filename_slug(context['customer'])}.pdf"
            relative_path = f"Finance/Invoices/{filename}"
            payload = business_file_payload("pdf", profile, context)
            write_bytes(output_dir / "files" / owner / relative_path, payload)
            records.append(
                file_manifest_record(
                    owner,
                    relative_path,
                    sha256_bytes(payload),
                    spec["dataset_license"],
                    creator=DATASET_CREATOR,
                    source="generated",
                    license_url=DATASET_LICENSE_URL,
                    document_id=invoice_number,
                    document_type="Customer Invoice",
                    subject=context["customer"],
                    synthetic=True,
                )
            )
            counts[owner] += 1


def generate_purchase_orders(
    spec: dict[str, Any],
    output_dir: Path,
    records: list[dict[str, Any]],
    counts: dict[str, int],
) -> None:
    configured_counts = {
        int(year): int(count) for year, count in spec["purchase_orders_per_user_by_year"].items()
    }
    linkage = {key: int(value) for key, value in spec["procurement_linkage"].items()}
    expected_linkage = {
        "requisitions_per_purchase_order": 1,
        "vendor_assessments_per_vendor_per_year": 1,
        "vendor_notes_per_vendor_per_year": 1,
        "vendor_master_records_per_vendor": 1,
    }
    if linkage != expected_linkage:
        raise ValueError(f"Unexpected procurement linkage configuration: {linkage}")
    if set(VENDOR_DETAILS) != set(VENDORS):
        raise ValueError("Vendor details do not cover the purchase-order vendor roster")
    anchor = date.fromisoformat(spec["calendar_anchor"])
    expected_years = set(range(min(configured_counts), anchor.year + 1))
    if set(configured_counts) != expected_years:
        raise ValueError(f"Purchase-order years must be consecutive through {anchor.year}")
    if any(count < 40 or count > 76 for count in configured_counts.values()):
        raise ValueError("Every yearly purchase-order count must be between 40 and 76")

    seed = int(spec["random_seed"])
    buyers = (f"{COMPANY_NAME} Research Operations", f"{COMPANY_NAME} Evaluation Lab")
    ship_to_locations = (
        "North Campus Receiving",
        "Operations Center Dock 2",
        "Customer Lab Receiving",
        "Downtown Office Mailroom",
    )
    payment_terms = ("Net 15", "Net 30", "Net 45", "Due on receipt")
    shipping_terms = ("FOB destination", "Prepaid ground", "Courier standard", "Inside delivery")
    statuses = ("Approved", "Issued", "Partially received", "Closed", "Awaiting delivery")

    for user_index, owner in enumerate(USERS):
        sequence = 0
        procurement_history: dict[tuple[int, str], list[dict[str, Any]]] = {}
        for year, yearly_count in sorted(configured_counts.items()):
            first_day = date(year, 1, 1)
            last_day = min(date(year, 12, 31), anchor) if year == anchor.year else date(year, 12, 31)
            available_days = (last_day - first_day).days + 1
            for yearly_index in range(yearly_count):
                sequence += 1
                rng = random.Random(seed + user_index * 1_000_003 + year * 10_007 + yearly_index * 101)
                day_offset = (yearly_index * 37 + rng.randrange(available_days)) % available_days
                record_date = first_day + timedelta(days=day_offset)
                required_date = record_date + timedelta(days=7 + rng.randrange(29))
                template_name = PURCHASE_ORDER_TEMPLATES[
                    (yearly_index + year + user_index) % len(PURCHASE_ORDER_TEMPLATES)
                ]
                vendor = VENDORS[(yearly_index * 3 + year + user_index) % len(VENDORS)]
                purchase_items = []
                used_items: set[int] = set()
                item_cursor = (yearly_index * 5 + year + user_index * 3) % len(PURCHASE_ORDER_ITEMS)
                while len(purchase_items) < 6:
                    item_index = item_cursor % len(PURCHASE_ORDER_ITEMS)
                    item_cursor += 3
                    if item_index in used_items:
                        item_cursor += 1
                        continue
                    used_items.add(item_index)
                    sku, description, base_price = PURCHASE_ORDER_ITEMS[item_index]
                    quantity = 1 + rng.randrange(12)
                    unit_price = base_price + rng.randrange(0, max(8, base_price // 8))
                    purchase_items.append(
                        {
                            "sku": sku,
                            "description": description,
                            "quantity": quantity,
                            "unit_price": unit_price,
                            "line_total": quantity * unit_price,
                        }
                    )

                subtotal = sum(item["line_total"] for item in purchase_items)
                shipping = 25 + rng.randrange(126)
                tax = round(subtotal * 0.08, 2)
                po_number = f"PO-{user_index + 1}-{year}-{yearly_index + 1:04d}"
                requisition_number = f"PRQ-{user_index + 1}-{year}-{yearly_index + 1:04d}"
                vendor_id = VENDOR_DETAILS[vendor]["vendor_id"]
                requested_date = record_date - timedelta(days=2 + rng.randrange(12))
                context = {
                    "purchase_order_number": po_number,
                    "requisition_number": requisition_number,
                    "vendor_id": vendor_id,
                    "buyer": buyers[user_index],
                    "vendor": vendor,
                    "ship_to": ship_to_locations[(yearly_index + user_index) % len(ship_to_locations)],
                    "record_date": record_date.isoformat(),
                    "required_date": required_date.isoformat(),
                    "payment_terms": payment_terms[(yearly_index + user_index) % len(payment_terms)],
                    "shipping_terms": shipping_terms[(yearly_index * 2 + user_index) % len(shipping_terms)],
                    "status": statuses[(yearly_index + year + user_index) % len(statuses)],
                    "requested_by": BUSINESS_NAMES[(sequence + user_index) % len(BUSINESS_NAMES)],
                    "approved_by": BUSINESS_NAMES[(sequence + user_index + 3) % len(BUSINESS_NAMES)],
                    "department": TEAMS[(yearly_index + year + user_index) % len(TEAMS)],
                    "cost_center": f"CC-{(year * 17 + yearly_index * 13 + user_index) % 900 + 100}",
                    "project": PROJECTS[(yearly_index * 7 + year + user_index) % len(PROJECTS)],
                    "purchase_items": purchase_items,
                    "subtotal": subtotal,
                    "shipping": shipping,
                    "tax": tax,
                    "total": subtotal + shipping + tax,
                }
                filename = f"Purchase_Order_{po_number}_{filename_slug(vendor)}.pdf"
                relative_path = f"Procurement/Purchase Orders/{year}/{filename}"
                payload = make_purchase_order_pdf(context, template_name)
                write_bytes(output_dir / "files" / owner / relative_path, payload)
                records.append(
                    file_manifest_record(
                        owner,
                        relative_path,
                        sha256_bytes(payload),
                        spec["dataset_license"],
                        creator=DATASET_CREATOR,
                        source="generated",
                        license_url=DATASET_LICENSE_URL,
                        document_id=po_number,
                        document_type="Purchase Order",
                        subject=vendor,
                        purchase_order_template=template_name,
                        purchase_order_year=year,
                        related_requisition=requisition_number,
                        procurement_record_key=f"{owner}:{po_number}",
                        vendor_id=vendor_id,
                        order_total=context["total"],
                        cost_center=context["cost_center"],
                        project=context["project"],
                        requested_by=context["requested_by"],
                        line_item_skus=[item["sku"] for item in purchase_items],
                        synthetic=True,
                    )
                )
                counts[owner] += 1

                requisition_body = "\n".join(
                    [
                        f"Requisition ID: {requisition_number}",
                        f"Related purchase order: {po_number}",
                        f"Procurement record key: {owner}:{po_number}",
                        f"Request date: {requested_date.isoformat()}",
                        f"Required date: {context['required_date']}",
                        f"Requested by: {context['requested_by']}",
                        f"Approved by: {context['approved_by']}",
                        f"Department: {context['department']}",
                        f"Cost center: {context['cost_center']}",
                        f"Project: {context['project']}",
                        f"Vendor: {vendor_id} | {vendor}",
                        "Status: Approved and converted to purchase order",
                        "",
                        "REQUESTED ITEMS",
                        *[
                            f"{item['sku']} | {item['description']} | qty {item['quantity']} | "
                            f"unit ${item['unit_price']:.2f} | line ${item['line_total']:.2f}"
                            for item in purchase_items
                        ],
                        "",
                        "COST SUMMARY",
                        f"Subtotal: ${context['subtotal']:.2f}",
                        f"Shipping: ${context['shipping']:.2f}",
                        f"Tax: ${context['tax']:.2f}",
                        f"Approved total: ${context['total']:.2f}",
                        "",
                        "APPROVAL AND LINKAGE",
                        f"This requisition was approved as {po_number} without changes to vendor, items, or total.",
                        "SYNTHETIC RESEARCH FIXTURE",
                    ]
                )
                requisition_extension = "pdf" if (yearly_index + year + user_index) % 2 == 0 else "docx"
                if requisition_extension == "pdf":
                    requisition_payload = make_pdf(
                        f"Purchase Requisition - {requisition_number}",
                        requisition_body,
                    )
                else:
                    requisition_payload = make_docx(
                        f"Purchase Requisition - {requisition_number}",
                        requisition_body,
                    )
                requisition_filename = (
                    f"Purchase_Requisition_{requisition_number}_for_{po_number}.{requisition_extension}"
                )
                requisition_path = f"Procurement/Purchase Requisitions/{year}/{requisition_filename}"
                write_bytes(output_dir / "files" / owner / requisition_path, requisition_payload)
                records.append(
                    file_manifest_record(
                        owner,
                        requisition_path,
                        sha256_bytes(requisition_payload),
                        spec["dataset_license"],
                        creator=DATASET_CREATOR,
                        source="generated",
                        license_url=DATASET_LICENSE_URL,
                        document_id=requisition_number,
                        document_type="Purchase Requisition",
                        subject=vendor,
                        related_purchase_order=po_number,
                        procurement_record_key=f"{owner}:{po_number}",
                        vendor_id=vendor_id,
                        order_total=context["total"],
                        cost_center=context["cost_center"],
                        project=context["project"],
                        requested_by=context["requested_by"],
                        line_item_skus=[item["sku"] for item in purchase_items],
                        synthetic=True,
                    )
                )
                counts[owner] += 1
                procurement_history.setdefault((year, vendor), []).append(
                    {
                        "purchase_order": po_number,
                        "requisition": requisition_number,
                        "total": context["total"],
                        "record_date": context["record_date"],
                        "required_date": context["required_date"],
                        "cost_center": context["cost_center"],
                        "project": context["project"],
                    }
                )

        for year in sorted(configured_counts):
            for vendor_index, vendor in enumerate(VENDORS):
                vendor_id = VENDOR_DETAILS[vendor]["vendor_id"]
                history = procurement_history.get((year, vendor), [])
                if not history:
                    raise ValueError(f"No purchase-order history for {owner}, {year}, {vendor}")
                purchase_order_ids = [entry["purchase_order"] for entry in history]
                annual_total = round(sum(float(entry["total"]) for entry in history), 2)
                average_total = round(annual_total / len(history), 2)
                quality_score = 88 + (year + vendor_index * 3 + user_index) % 12
                on_time_rate = 86 + (year * 2 + vendor_index + user_index) % 14
                exception_count = (year + vendor_index + user_index) % 4
                assessment_id = f"ASSESS-{user_index + 1}-{year}-{vendor_id}"
                assessment_body = "\n".join(
                    [
                        f"Assessment ID: {assessment_id}",
                        f"Assessment year: {year}",
                        f"Vendor: {vendor_id} | {vendor}",
                        f"Category: {VENDOR_DETAILS[vendor]['category']}",
                        f"Purchase orders reviewed: {len(history)}",
                        f"Annual ordered value: ${annual_total:.2f}",
                        f"Average order value: ${average_total:.2f}",
                        f"Quality score: {quality_score}/100",
                        f"On-time delivery rate: {on_time_rate}%",
                        f"Recorded delivery exceptions: {exception_count}",
                        "Risk rating: Low" if quality_score >= 92 else "Risk rating: Moderate",
                        "Recommendation: Retain as an approved vendor for the next review period.",
                        "",
                        "LINKED PURCHASE ORDERS",
                        *purchase_order_ids,
                        "",
                        "SYNTHETIC RESEARCH FIXTURE",
                    ]
                )
                assessment_extension = "pdf" if (year + vendor_index + user_index) % 2 == 0 else "docx"
                if assessment_extension == "pdf":
                    assessment_payload = make_pdf(
                        f"Vendor Assessment - {assessment_id}",
                        assessment_body,
                    )
                else:
                    assessment_payload = make_docx(
                        f"Vendor Assessment - {assessment_id}",
                        assessment_body,
                    )
                assessment_filename = (
                    f"Vendor_Assessment_{assessment_id}_{filename_slug(vendor)}.{assessment_extension}"
                )
                assessment_path = f"Procurement/Vendor Assessments/{year}/{assessment_filename}"
                write_bytes(output_dir / "files" / owner / assessment_path, assessment_payload)
                records.append(
                    file_manifest_record(
                        owner,
                        assessment_path,
                        sha256_bytes(assessment_payload),
                        spec["dataset_license"],
                        creator=DATASET_CREATOR,
                        source="generated",
                        license_url=DATASET_LICENSE_URL,
                        document_id=assessment_id,
                        document_type="Vendor Assessment",
                        subject=vendor,
                        vendor_id=vendor_id,
                        assessment_year=year,
                        purchase_order_count=len(history),
                        purchase_order_total=annual_total,
                        related_purchase_orders=purchase_order_ids,
                        synthetic=True,
                    )
                )
                counts[owner] += 1

                note_id = f"VNOTE-{user_index + 1}-{year}-{vendor_id}"
                note_body = "\n".join(
                    [
                        f"Vendor Note: {note_id}",
                        f"Vendor: {vendor_id} | {vendor}",
                        f"Year: {year}",
                        f"Related assessment: {assessment_id}",
                        f"Purchase orders: {len(history)}",
                        f"Ordered value: ${annual_total:.2f}",
                        f"Quality score: {quality_score}/100",
                        f"On-time delivery: {on_time_rate}%",
                        "Summary: Annual purchasing activity reconciles with the linked assessment and master record.",
                        f"Recent purchase order: {purchase_order_ids[-1]}",
                        "Action: Continue standard monitoring and review exceptions at the next quarterly meeting.",
                        "SYNTHETIC RESEARCH FIXTURE",
                        "",
                    ]
                ).encode()
                note_filename = f"Vendor_Note_{note_id}_{filename_slug(vendor)}.txt"
                note_path = f"Procurement/Vendor Notes/{year}/{note_filename}"
                write_bytes(output_dir / "files" / owner / note_path, note_body)
                records.append(
                    file_manifest_record(
                        owner,
                        note_path,
                        sha256_bytes(note_body),
                        spec["dataset_license"],
                        creator=DATASET_CREATOR,
                        source="generated",
                        license_url=DATASET_LICENSE_URL,
                        document_id=note_id,
                        document_type="Vendor Review Note",
                        subject=vendor,
                        vendor_id=vendor_id,
                        review_year=year,
                        related_assessment=assessment_id,
                        purchase_order_count=len(history),
                        purchase_order_total=annual_total,
                        synthetic=True,
                    )
                )
                counts[owner] += 1

        for vendor_index, vendor in enumerate(VENDORS):
            vendor_id = VENDOR_DETAILS[vendor]["vendor_id"]
            vendor_history = [
                entry
                for (year, history_vendor), entries in procurement_history.items()
                if history_vendor == vendor
                for entry in entries
            ]
            vendor_history.sort(key=lambda entry: (entry["record_date"], entry["purchase_order"]))
            annual_summary = {}
            for year in sorted(configured_counts):
                year_entries = procurement_history[(year, vendor)]
                annual_summary[str(year)] = {
                    "purchase_order_count": len(year_entries),
                    "purchase_order_total": round(sum(float(entry["total"]) for entry in year_entries), 2),
                    "assessment_id": f"ASSESS-{user_index + 1}-{year}-{vendor_id}",
                    "vendor_note_id": f"VNOTE-{user_index + 1}-{year}-{vendor_id}",
                }
            lifetime_total = round(sum(float(entry["total"]) for entry in vendor_history), 2)
            annual_history_lines = [
                (
                    f"{year}: {summary['purchase_order_count']} purchase orders | "
                    f"${summary['purchase_order_total']:,.2f} ordered | "
                    f"Assessment {summary['assessment_id']} | Note {summary['vendor_note_id']}"
                )
                for year, summary in annual_summary.items()
            ]
            purchase_order_lines = [
                (
                    f"{entry['purchase_order']} | {entry['record_date']} | "
                    f"${float(entry['total']):,.2f} | {entry['project']} | {entry['cost_center']}"
                )
                for entry in vendor_history
            ]
            master_body = "\n".join(
                [
                    "VENDOR PROFILE",
                    f"Vendor ID: {vendor_id}",
                    f"Vendor name: {vendor}",
                    f"Category: {VENDOR_DETAILS[vendor]['category']}",
                    "Status: Active - Approved",
                    f"Ordering email: orders@{filename_slug(vendor).lower()}.cedarstone.test",
                    "Address: 480 Commerce Park, Toronto, Ontario",
                    f"Default payment terms: {payment_terms[vendor_index % len(payment_terms)]}",
                    f"Record owner: {owner}",
                    "",
                    "PROCUREMENT SUMMARY",
                    f"Purchase orders: {len(vendor_history)}",
                    f"Lifetime ordered value: ${lifetime_total:,.2f}",
                    f"History period: {min(annual_summary)}-{max(annual_summary)}",
                    "",
                    "ANNUAL PURCHASING HISTORY",
                    *annual_history_lines,
                    "",
                    "LINKED PURCHASE ORDER INDEX",
                    "Purchase order | Date | Approved total | Project | Cost center",
                    *purchase_order_lines,
                    "",
                    "DATA GOVERNANCE",
                    "This readable vendor master record is a deterministic synthetic research fixture.",
                    "The provenance manifest contains the corresponding structured fields and SHA-256 hash.",
                ]
            )
            master_payload = make_docx(f"Vendor Master Record - {vendor_id}", master_body)
            master_filename = f"Vendor_Master_{vendor_id}_{filename_slug(vendor)}.docx"
            master_path = f"Procurement/Vendor Master Data/{master_filename}"
            write_bytes(output_dir / "files" / owner / master_path, master_payload)
            records.append(
                file_manifest_record(
                    owner,
                    master_path,
                    sha256_bytes(master_payload),
                    spec["dataset_license"],
                    creator=DATASET_CREATOR,
                    source="generated",
                    license_url=DATASET_LICENSE_URL,
                    document_id=vendor_id,
                    document_type="Vendor Master Record",
                    subject=vendor,
                    vendor_id=vendor_id,
                    purchase_order_count=len(vendor_history),
                    purchase_order_total=lifetime_total,
                    annual_summary=annual_summary,
                    related_purchase_orders=[entry["purchase_order"] for entry in vendor_history],
                    synthetic=True,
                )
            )
            counts[owner] += 1


def generate_timesheets(
    spec: dict[str, Any],
    output_dir: Path,
    records: list[dict[str, Any]],
    counts: dict[str, int],
) -> None:
    configured_counts = {
        int(year): int(count) for year, count in spec["timesheets_per_user_by_year"].items()
    }
    anchor = date.fromisoformat(spec["calendar_anchor"])
    expected_years = set(range(min(configured_counts), anchor.year + 1))
    if set(configured_counts) != expected_years:
        raise ValueError(f"Timesheet years must be consecutive through {anchor.year}")
    if any(count != 12 for year, count in configured_counts.items() if year < anchor.year):
        raise ValueError("Every completed timesheet year must contain 12 monthly workbooks")
    if configured_counts[anchor.year] != 6:
        raise ValueError(f"The {anchor.year} timesheet seed must stop after June")

    categories = tuple(spec["timesheet_worker_categories"])
    if categories != tuple(TIMESHEET_WORKERS):
        raise ValueError("Timesheet worker categories do not match the supported category roster")
    if any(not workers for workers in TIMESHEET_WORKERS.values()):
        raise ValueError("Every timesheet worker category must contain workers")

    month_names = (
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    )
    category_prefixes = {
        "Full-Time Employees": "FTE",
        "Part-Time Employees": "PTE",
        "Contractors": "CTR",
        "Interns": "INT",
        "Temporary Staff": "TMP",
        "Consultants": "CNS",
    }
    base_hours = {
        "Full-Time Employees": 160,
        "Part-Time Employees": 80,
        "Contractors": 128,
        "Interns": 120,
        "Temporary Staff": 144,
        "Consultants": 72,
    }
    seed = int(spec["random_seed"])

    for user_index, owner in enumerate(USERS):
        for year, month_count in sorted(configured_counts.items()):
            for month in range(1, month_count + 1):
                category_rows: dict[str, list[list[str | int | float]]] = {}
                for category_index, category in enumerate(categories):
                    rows: list[list[str | int | float]] = []
                    for worker_index, worker_name in enumerate(TIMESHEET_WORKERS[category], start=1):
                        rng = random.Random(
                            seed
                            + user_index * 1_000_003
                            + year * 10_007
                            + month * 503
                            + category_index * 97
                            + worker_index * 17
                        )
                        regular_hours = base_hours[category] + rng.randrange(-8, 9)
                        overtime_hours = rng.randrange(0, 13)
                        leave_hours = (0, 0, 0, 8, 16)[rng.randrange(5)]
                        total_hours = regular_hours + overtime_hours + leave_hours
                        approval_status = (
                            "Approved",
                            "Approved",
                            "Manager Confirmed",
                            "Pending Review",
                        )[(month + category_index + worker_index + user_index) % 4]
                        rows.append(
                            [
                                f"{category_prefixes[category]}-{user_index + 1}{worker_index:03d}",
                                worker_name,
                                category,
                                f"CC-{(year * 13 + category_index * 31 + worker_index * 7) % 900 + 100}",
                                regular_hours,
                                overtime_hours,
                                leave_hours,
                                total_hours,
                                approval_status,
                            ]
                        )
                    category_rows[category] = rows

                period = f"{year}-{month:02d}"
                title = f"Monthly Timesheet - {month_names[month - 1]} {year}"
                payload = make_timesheet_xlsx(title, period, owner, category_rows)
                filename = f"Timesheet_{period}_{month_names[month - 1]}.xlsx"
                relative_path = f"People/Timesheets/{year}/{filename}"
                write_bytes(output_dir / "files" / owner / relative_path, payload)
                records.append(
                    file_manifest_record(
                        owner,
                        relative_path,
                        sha256_bytes(payload),
                        spec["dataset_license"],
                        creator=DATASET_CREATOR,
                        source="generated",
                        license_url=DATASET_LICENSE_URL,
                        document_id=f"TIME-{user_index + 1}-{period}",
                        document_type="Monthly Timesheet",
                        subject=period,
                        timesheet_year=year,
                        timesheet_month=month,
                        worker_categories=list(categories),
                        synthetic=True,
                    )
                )
                counts[owner] += 1


def generate_root_work_files(
    spec: dict[str, Any],
    output_dir: Path,
    records: list[dict[str, Any]],
    counts: dict[str, int],
) -> None:
    configured_count = int(spec["root_work_files_per_user"])
    root_definitions = (
        ("md", "Project Status Report"),
        ("docx", "Meeting Report"),
        ("xlsx", "Budget Forecast"),
        ("csv", "Sales Order Register"),
        ("pptx", "Operations Review"),
    )
    if configured_count != len(root_definitions) + 1:
        raise ValueError("Root work-file count must include one purchase-order copy and five current work files")

    anchor = date.fromisoformat(spec["calendar_anchor"])
    seed = int(spec["random_seed"])
    for user_index, owner in enumerate(USERS):
        purchase_orders = [
            record
            for record in records
            if record.get("owner") == owner
            and record.get("document_type") == "Purchase Order"
            and int(record.get("purchase_order_year", 0)) == anchor.year
        ]
        if not purchase_orders:
            raise ValueError(f"No current-year purchase order available for {owner}'s root work files")
        rng = random.Random(seed + user_index * 1_000_003 + 71_039)
        purchase_order = purchase_orders[rng.randrange(len(purchase_orders))]
        source_path = output_dir / "files" / owner / purchase_order["path"]
        purchase_order_payload = source_path.read_bytes()
        purchase_order_copy_path = (
            f"Purchase Order - {purchase_order['document_id']} - Quick Copy.pdf"
        )
        write_bytes(output_dir / "files" / owner / purchase_order_copy_path, purchase_order_payload)
        records.append(
            file_manifest_record(
                owner,
                purchase_order_copy_path,
                sha256_bytes(purchase_order_payload),
                spec["dataset_license"],
                creator=DATASET_CREATOR,
                source="generated",
                license_url=DATASET_LICENSE_URL,
                document_id=f"ROOT-COPY-{purchase_order['document_id']}",
                document_type="Purchase Order Reference Copy",
                subject=purchase_order["subject"],
                related_purchase_order=purchase_order["document_id"],
                original_path=purchase_order["path"],
                root_work_file=True,
                synthetic=True,
            )
        )
        counts[owner] += 1

        for index, (extension, document_type) in enumerate(root_definitions):
            profile = next(
                profile
                for profile in BUSINESS_DOCUMENT_PROFILES[extension]
                if profile["label"] == document_type
            )
            record_date = anchor - timedelta(days=index + user_index * 2)
            context = build_business_context(
                profile,
                owner,
                user_index,
                60_000 + index,
                record_date,
                seed,
            )
            if document_type == "Project Status Report":
                filename = f"Project Status - {context['project']} - July 2026.md"
            elif document_type == "Meeting Report":
                filename = f"Meeting Brief - {context['team']} - {record_date.isoformat()}.docx"
            elif document_type == "Budget Forecast":
                filename = f"Q3 Budget Forecast - {context['team']}.xlsx"
            elif document_type == "Sales Order Register":
                filename = f"Open Sales Orders - {context['customer']} - July 2026.csv"
            else:
                filename = f"Operations Review - {context['team']} - July 2026.pptx"
            payload = business_file_payload(extension, profile, context)
            write_bytes(output_dir / "files" / owner / filename, payload)
            records.append(
                file_manifest_record(
                    owner,
                    filename,
                    sha256_bytes(payload),
                    spec["dataset_license"],
                    creator=DATASET_CREATOR,
                    source="generated",
                    license_url=DATASET_LICENSE_URL,
                    document_id=context["document_id"],
                    document_type=document_type,
                    subject=context["subject"],
                    root_work_file=True,
                    synthetic=True,
                )
            )
            counts[owner] += 1


def generate_bulk_files(spec: dict[str, Any], output_dir: Path, records: list[dict[str, Any]], counts: dict[str, int]) -> None:
    target = int(spec["targets"]["files_per_user"])
    configured_folders = tuple(spec["business_workspace_folders"])
    if configured_folders != BUSINESS_FOLDERS:
        raise ValueError(f"Unexpected business folder taxonomy: {configured_folders}")
    managed_targets = spec["managed_folder_targets"]
    if set(managed_targets) != set(USERS):
        raise ValueError("Managed folder targets must cover both seeded users")
    anchor = date.fromisoformat(spec["calendar_anchor"])
    seed = int(spec["random_seed"])

    for user_index, owner in enumerate(USERS):
        owner_targets = {folder: int(count) for folder, count in managed_targets[owner].items()}
        if any(count < 100 or count > 400 for count in owner_targets.values()):
            raise ValueError(f"Managed folder target outside 100-400 range for {owner}")
        sequence = 0
        for folder, folder_target in owner_targets.items():
            folder_root = output_dir / "files" / owner / folder
            existing_count = sum(1 for path in folder_root.rglob("*") if path.is_file()) if folder_root.exists() else 0
            needed = folder_target - existing_count
            if needed < 0:
                raise ValueError(
                    f"Existing file count for {owner}/{folder} is {existing_count}; target is {folder_target}"
                )
            folder_profiles = [
                (extension, profile)
                for extension, profiles in BUSINESS_DOCUMENT_PROFILES.items()
                for profile in profiles
                if f"{profile['area']}/{profile['category']}" == folder
            ]
            if needed and not folder_profiles:
                raise ValueError(f"No document profile can fill managed folder {folder}")
            for folder_index in range(needed):
                extension, profile = folder_profiles[(folder_index + user_index) % len(folder_profiles)]
                index = 100_000 + sequence
                sequence += 1
                record_date = anchor - timedelta(days=(index * 3 + user_index * 11) % 1461)
                context = build_business_context(profile, owner, user_index, index, record_date, seed)
                filename = (
                    f"{filename_slug(profile['label'])}_{context['document_id']}_"
                    f"{filename_slug(context['subject'])}.{extension}"
                )
                relative_path = f"{folder}/{filename}"
                payload = business_file_payload(extension, profile, context)
                lowered = payload.decode("latin-1", "ignore").lower()
                if any(term in lowered for term in RESERVED_BULK_TERMS):
                    raise ValueError(f"Reserved benchmark term appeared in {relative_path}")
                write_bytes(output_dir / "files" / owner / relative_path, payload)
                records.append(
                    file_manifest_record(
                        owner,
                        relative_path,
                        sha256_bytes(payload),
                        spec["dataset_license"],
                        creator=DATASET_CREATOR,
                        source="generated",
                        license_url=DATASET_LICENSE_URL,
                        document_id=context["document_id"],
                        document_type=profile["label"],
                        subject=context["subject"],
                        prepared_by=context["prepared_by"],
                        customer=context["customer"],
                        vendor=context["vendor"],
                        project=context["project"],
                        team=context["team"],
                        record_date=context["record_date"],
                        managed_folder=folder,
                        synthetic=True,
                    )
                )
                counts[owner] += 1

            final_count = sum(1 for path in folder_root.rglob("*") if path.is_file())
            if final_count != folder_target:
                raise ValueError(f"Managed folder count mismatch for {owner}/{folder}: {final_count}")

        if counts[owner] != target:
            raise ValueError(f"Managed folder allocation produced {counts[owner]} files for {owner}; expected {target}")


def vcard_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def make_vcard(uid: str, name: str, email: str, phone: str, nickname: str = "") -> bytes:
    parts = name.split(maxsplit=1)
    given = parts[0]
    family = parts[1] if len(parts) > 1 else ""
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        "PRODID:-//WebArena-Pro//Nextcloud Seed v2//EN",
        f"UID:{vcard_escape(uid)}",
        f"FN:{vcard_escape(name)}",
        f"N:{vcard_escape(family)};{vcard_escape(given)};;;",
        f"ORG:{vcard_escape(COMPANY_NAME)}",
    ]
    if nickname:
        lines.append(f"NICKNAME:{vcard_escape(nickname)}")
    lines.extend([f"EMAIL;TYPE=INTERNET:{email}", f"TEL;TYPE=CELL:{phone}", "END:VCARD", ""])
    return "\r\n".join(lines).encode()


def generate_contacts(spec: dict[str, Any], output_dir: Path, records: list[dict[str, Any]]) -> None:
    target = int(spec["targets"]["contacts_per_user"])
    for owner_index, owner in enumerate(USERS):
        contacts: list[tuple[str, str, str, str]] = [(*item, "") for item in SHARED_CONTACTS]
        contacts.extend((*item, "") for item in AGENT_CONTACTS[owner])
        contacts.extend(SYNTHETIC_CONTACTS[owner])
        additional_count = target - len(contacts)
        if additional_count < 0:
            raise ValueError(f"Contact target for {owner} is lower than the required contact set")
        if additional_count > len(ADDITIONAL_CONTACT_GIVEN_NAMES) * len(ADDITIONAL_CONTACT_FAMILY_NAMES):
            raise ValueError(f"Contact target for {owner} exceeds the deterministic name pool")
        for index in range(additional_count):
            given_name = ADDITIONAL_CONTACT_GIVEN_NAMES[index % len(ADDITIONAL_CONTACT_GIVEN_NAMES)]
            family_name = ADDITIONAL_CONTACT_FAMILY_NAMES[
                (index * 7 + owner_index * 11) % len(ADDITIONAL_CONTACT_FAMILY_NAMES)
            ]
            email = f"{given_name.lower()}.{family_name.lower()}.{owner}@{COMPANY_DOMAIN}"
            phone = f"555-{600 + owner_index * 100 + index:04d}"
            contacts.append((f"{given_name} {family_name}", email, phone, ""))
        if len(contacts) != target:
            raise ValueError(f"Contact target mismatch for {owner}: {len(contacts)} != {target}")
        if len({email for _, email, _, _ in contacts}) != target:
            raise ValueError(f"Duplicate contact email generated for {owner}")
        if len({phone for _, _, phone, _ in contacts}) != target:
            raise ValueError(f"Duplicate contact phone generated for {owner}")
        for index, (name, email, phone, nickname) in enumerate(contacts):
            uid = f"webarena-v2-{owner}-contact-{index:03d}"
            payload = make_vcard(uid, name, email, phone, nickname)
            path = output_dir / "contacts" / owner / f"{uid}.vcf"
            write_bytes(path, payload)
            records.append(
                {
                    "entity_type": "contact",
                    "owner": owner,
                    "uid": uid,
                    "display_name": name,
                    "email": email,
                    "phone": phone,
                    "sha256": sha256_bytes(payload),
                    "license": spec["dataset_license"],
                    "creator": DATASET_CREATOR,
                    "source": "generated",
                    "license_url": DATASET_LICENSE_URL,
                    "generator_version": GENERATOR_VERSION,
                }
            )


def ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def make_ics(
    uid: str,
    title: str,
    description: str,
    start: datetime,
    recurrence: str = "",
    location: str = "",
    duration_minutes: int = 45,
    timezone_id: str = "America/Toronto",
    attendees: Iterable[tuple[str, str]] = (),
) -> bytes:
    end = start + timedelta(minutes=duration_minutes)
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//WebArena-Pro//Nextcloud Seed v2//EN",
        "CALSCALE:GREGORIAN",
        f"X-WR-TIMEZONE:{timezone_id}",
        "BEGIN:VTIMEZONE",
        f"TZID:{timezone_id}",
        f"X-LIC-LOCATION:{timezone_id}",
        "BEGIN:DAYLIGHT",
        "TZOFFSETFROM:-0500",
        "TZOFFSETTO:-0400",
        "TZNAME:EDT",
        "DTSTART:20260308T020000",
        "END:DAYLIGHT",
        "BEGIN:STANDARD",
        "TZOFFSETFROM:-0400",
        "TZOFFSETTO:-0500",
        "TZNAME:EST",
        "DTSTART:20261101T020000",
        "END:STANDARD",
        "END:VTIMEZONE",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp.strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;TZID={timezone_id}:{start.strftime('%Y%m%dT%H%M%S')}",
        f"DTEND;TZID={timezone_id}:{end.strftime('%Y%m%dT%H%M%S')}",
        f"SUMMARY:{ics_escape(title)}",
        f"DESCRIPTION:{ics_escape(description)}",
        f"LOCATION:{ics_escape(location)}",
        "STATUS:CONFIRMED",
        "TRANSP:OPAQUE",
        "CATEGORIES:BUSINESS,MEETING",
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ]
    event_end_index = lines.index("END:VEVENT")
    attendee_lines = [
        f"ATTENDEE;CN={ics_escape(name)};ROLE=REQ-PARTICIPANT:mailto:{email}"
        for name, email in attendees
    ]
    lines[event_end_index:event_end_index] = attendee_lines
    if recurrence:
        lines.insert(lines.index("END:VEVENT"), f"RRULE:{recurrence}")
    return "\r\n".join(lines).encode()


def generate_calendars(spec: dict[str, Any], output_dir: Path, records: list[dict[str, Any]]) -> None:
    target = int(spec["targets"]["calendar_events_per_user"])
    anchor = date.fromisoformat(spec["calendar_anchor"])
    weekday_codes = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
    recurring_indexes = {0, 1, 4, 6, 7, 9, 15, 19}

    def business_day(start: date, offset: int) -> date:
        current = start
        remaining = offset
        while remaining:
            current += timedelta(days=1)
            if current.weekday() < 5:
                remaining -= 1
        return current

    for user_index, owner in enumerate(USERS):
        owner_contacts = [
            record
            for record in records
            if record.get("entity_type") == "contact" and record.get("owner") == owner
        ]
        owner_files = sorted(
            (
                record
                for record in records
                if record.get("entity_type") == "file"
                and record.get("owner") == owner
                and record.get("document_id")
            ),
            key=lambda record: record["path"],
        )
        if len(owner_contacts) < 3 or not owner_files:
            raise ValueError(f"Calendar linkage inputs are incomplete for {owner}")
        events = [*SHARED_EVENTS, *AGENT_EVENTS[owner]]
        for index, (title, description) in enumerate(PUNCTUAL_EVENTS):
            subject_options = (CUSTOMERS[index % len(CUSTOMERS)], PROJECTS[index % len(PROJECTS)], VENDORS[index % len(VENDORS)], TEAMS[index % len(TEAMS)])
            events.append((f"{title} - {subject_options[index % len(subject_options)]}", description))
        if len(events) != target:
            raise ValueError(f"Calendar target mismatch for {owner}: {len(events)} != {target}")
        for index, (title, description) in enumerate(events):
            related_customer = CUSTOMERS[index % len(CUSTOMERS)]
            related_project = PROJECTS[index % len(PROJECTS)]
            related_vendor = VENDORS[index % len(VENDORS)]
            related_team = TEAMS[index % len(TEAMS)]
            linked_file = owner_files[(index * 83 + user_index * 17) % len(owner_files)]
            attendee_records = [
                owner_contacts[(index + offset * 7) % len(owner_contacts)] for offset in range(3)
            ]
            linked_description = (
                f"{description} Related customer: {related_customer}. Related project: {related_project}. "
                f"Related vendor: {related_vendor}. Responsible team: {related_team}. "
                f"Related file: {linked_file['path']}."
            )
            event_date = business_day(anchor, index // 4)
            hours = (9, 10, 13, 15)
            minutes = (0, 30, 0, 30)
            start = datetime.combine(
                event_date,
                time(hours[index % 4], minutes[index % 4]),
            )
            recurrence = ""
            if index in recurring_indexes - {6, 9, 15}:
                recurrence = f"FREQ=WEEKLY;COUNT=12;BYDAY={weekday_codes[event_date.weekday()]}"
            elif index == 6:
                recurrence = "FREQ=DAILY;COUNT=10;BYDAY=MO,TU,WE,TH,FR"
            elif index in {9, 15}:
                recurrence = f"FREQ=MONTHLY;COUNT=6;BYMONTHDAY={event_date.day}"
            uid = f"webarena-v2-{owner}-event-{index:03d}"
            payload = make_ics(
                uid,
                title,
                linked_description,
                start,
                recurrence=recurrence,
                location=("Video Conference", "Meeting Room Cedar", "Meeting Room Harbor", "Focus Room 2")[index % 4],
                duration_minutes=(30, 45, 60, 45)[index % 4],
                attendees=[(record["display_name"], record["email"]) for record in attendee_records],
            )
            write_bytes(output_dir / "calendars" / owner / f"{uid}.ics", payload)
            records.append(
                {
                    "entity_type": "calendar_event",
                    "owner": owner,
                    "uid": uid,
                    "title": title,
                    "recurrence": recurrence,
                    "attendee_contact_uids": [record["uid"] for record in attendee_records],
                    "related_file_owner": owner,
                    "related_file": linked_file["path"],
                    "related_file_sha256": linked_file["sha256"],
                    "related_customer": related_customer,
                    "related_project": related_project,
                    "related_vendor": related_vendor,
                    "related_team": related_team,
                    "sha256": sha256_bytes(payload),
                    "license": spec["dataset_license"],
                    "creator": DATASET_CREATOR,
                    "source": "generated",
                    "license_url": DATASET_LICENSE_URL,
                    "generator_version": GENERATOR_VERSION,
                }
            )


def generate_talk(spec: dict[str, Any], output_dir: Path, records: list[dict[str, Any]]) -> None:
    rooms = list(spec["talk_rooms"])
    additional_rooms = list(spec["additional_talk_rooms"])
    all_rooms = rooms + additional_rooms + ["Project Alpha"]
    target = int(spec["targets"]["talk_messages_total"])
    expected_author_counts = {owner: int(count) for owner, count in spec["targets"]["talk_messages_by_author"].items()}
    talk_users = dict(spec["talk_users"])
    support_by_room = dict(spec["talk_room_support_authors"])
    unread_by_user = dict(spec["talk_unread_messages"])
    if len(rooms) != 4 or len(additional_rooms) != 5:
        raise ValueError("Talk seed requires four baseline rooms and five additional conversation rooms")
    if set(talk_users) != set(TALK_USERS):
        raise ValueError("Talk users do not match the supported deterministic user set")
    if set(support_by_room) != set(all_rooms):
        raise ValueError("Talk room support-author configuration is incomplete")
    if set(rooms) != set(BASELINE_TALK_TOPICS):
        raise ValueError("Baseline Talk rooms do not match their conversation topics")
    if set(additional_rooms) != set(ADDITIONAL_TALK_TOPICS):
        raise ValueError("Additional Talk rooms do not match their conversation topics")

    support_totals = {
        user: sum(int(room_counts.get(user, 0)) for room_counts in support_by_room.values())
        for user in SUPPORT_USERS
    }
    if support_totals != {user: expected_author_counts[user] for user in SUPPORT_USERS}:
        raise ValueError(f"Talk support-user allocation does not match targets: {support_totals}")

    phase_templates = (
        "Let's use this thread to review {subject}. I want the open questions and decision owner in one place.",
        "I reviewed {subject} this morning. {finding}",
        "That matches what I saw. Could we also verify the supporting evidence before we make the change?",
        "Yes. The most useful next step is to {action}.",
        "I can take that action and post the result here so everyone has the same context.",
        "Please include the owner and due date in the update; that will make the handoff easier to track.",
        "Good point. I have added both and checked the dependency with the team responsible for the next step.",
        "I reviewed the update and do not see another blocker. The remaining condition is that {completion}.",
        "Thanks. I'll keep this thread open until that condition is confirmed and then record the final decision.",
        "Agreed. This gives us a clear audit trail and avoids splitting the follow-up across separate messages.",
    )

    def round_robin_support(room: str) -> list[str]:
        remaining = {author: int(count) for author, count in support_by_room[room].items()}
        authors: list[str] = []
        while any(remaining.values()):
            for author in remaining:
                if remaining[author] > 0:
                    authors.append(author)
                    remaining[author] -= 1
        return authors

    def interleave_authors(agent_authors: list[str], support_authors: list[str]) -> list[str]:
        total = len(agent_authors) + len(support_authors)
        support_positions = {
            ((index + 1) * (total + 1) // (len(support_authors) + 1)) - 1
            for index in range(len(support_authors))
        }
        if len(support_positions) != len(support_authors):
            raise ValueError("Unable to distribute Talk support authors")
        agent_iterator = iter(agent_authors)
        support_iterator = iter(support_authors)
        return [next(support_iterator) if index in support_positions else next(agent_iterator) for index in range(total)]

    messages: list[tuple[str, str, str, str, str, str]] = []

    def add_room_history(room_index: int, room: str, topics: tuple[tuple[str, str, str, str], ...], agent_authors: list[str]) -> None:
        authors = interleave_authors(agent_authors, round_robin_support(room))
        base_size, larger_blocks = divmod(len(authors), len(topics))
        block_sizes = [base_size + (1 if index < larger_blocks else 0) for index in range(len(topics))]
        position = 0
        for topic_index, (subject, finding, action, completion) in enumerate(topics):
            root_key = f"room-{room_index:02d}-message-{position + 1:03d}"
            thread_title = subject.removeprefix("the ").removeprefix("next ").capitalize()
            for phase_index in range(block_sizes[topic_index]):
                message_key = f"room-{room_index:02d}-message-{position + 1:03d}"
                reply_to = "" if phase_index == 0 else root_key
                title = thread_title if phase_index == 0 else ""
                message = phase_templates[phase_index % len(phase_templates)].format(
                    subject=subject,
                    finding=finding,
                    action=action,
                    completion=completion,
                )
                messages.append((room, authors[position], message_key, reply_to, title, message))
                position += 1

    for room_index, room in enumerate(rooms):
        agent_authors = [USERS[(index + room_index) % 2] for index in range(48)]
        add_room_history(room_index, room, BASELINE_TALK_TOPICS[room], agent_authors)

    for additional_index, room in enumerate(additional_rooms):
        agent_authors = []
        for index in range(29):
            author = USERS[index % 2]
            if additional_index < 3 and index == 1:
                author = "maya.patel"
            agent_authors.append(author)
        add_room_history(len(rooms) + additional_index, room, ADDITIONAL_TALK_TOPICS[room], agent_authors)

    for index, (author, message) in enumerate(CANONICAL_MESSAGES, start=1):
        messages.append(("Project Alpha", author, f"project-alpha-{index:03d}", "", "", message))

    if len(messages) != target:
        raise ValueError(f"Talk message target mismatch: {len(messages)} != {target}")
    author_counts = {owner: sum(1 for _, author, _, _, _, _ in messages if author == owner) for owner in TALK_USERS}
    if author_counts != expected_author_counts:
        raise ValueError(f"Talk author counts do not match target: {author_counts} != {expected_author_counts}")

    room_file_prefixes = {
        "Research Updates": "Analytics/Order Plots/",
        "Operations Planning": "Operations/Daily Operations/",
        "Product Coordination": "Projects/Status Reports/",
        "Design Exchange": "Presentations/Quarterly Reviews/",
        "Finance and Invoices": "Finance/Invoices/",
        "Customer Launches": "Sales/Orders/",
        "Office Operations": "Procurement/Purchase Orders/",
        "Hiring Coordination": "People/Recruiting/",
        "Events and Travel": "Meetings/Meeting Reports/",
        "Project Alpha": "work/Project_Alpha_Notes.txt",
    }
    room_file_links: dict[str, dict[str, dict[str, str]]] = {}
    for room, prefix in room_file_prefixes.items():
        room_file_links[room] = {}
        for owner in USERS:
            candidates = sorted(
                (
                    record
                    for record in records
                    if record.get("entity_type") == "file"
                    and record.get("owner") == owner
                    and record.get("path", "").startswith(prefix)
                ),
                key=lambda record: record["path"],
            )
            if not candidates:
                raise ValueError(f"No linked file available for Talk room {room} and {owner}")
            linked = candidates[len(room_file_links) % len(candidates)]
            room_file_links[room][owner] = {
                "path": linked["path"],
                "sha256": linked["sha256"],
            }

    talk_dir = output_dir / "talk"
    talk_dir.mkdir(parents=True, exist_ok=True)
    with (talk_dir / "messages.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        for ordinal, (room, author, message_key, reply_to, thread_title, message) in enumerate(messages, start=1):
            linked_files = room_file_links[room]
            rendered_message = message
            if room != "Project Alpha" and not reply_to:
                rendered_message += (
                    f" Related files: maya.patel/{linked_files['maya.patel']['path']} and "
                    f"daniel.brooks/{linked_files['daniel.brooks']['path']}."
                )
            writer.writerow([room, author, message_key, reply_to or "-", thread_title or "-", rendered_message])
            records.append(
                {
                    "entity_type": "talk_message",
                    "room": room,
                    "author": author,
                    "ordinal": ordinal,
                    "message_key": message_key,
                    "reply_to": reply_to,
                    "thread_title": thread_title,
                    "sha256": sha256_bytes(rendered_message.encode()),
                    "related_files": linked_files,
                    "license": spec["dataset_license"],
                    "creator": DATASET_CREATOR,
                    "source": "generated",
                    "license_url": DATASET_LICENSE_URL,
                    "generator_version": GENERATOR_VERSION,
                }
            )

    with (talk_dir / "rooms.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        for room in all_rooms:
            participants = [*USERS, *support_by_room[room].keys()]
            if len(participants) < 3 and room != "Project Alpha":
                raise ValueError(f"Talk room {room} needs at least three participants")
            writer.writerow([room, ",".join(participants)])

    with (talk_dir / "unread.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        for user, unread_rooms in unread_by_user.items():
            for room, unread_count in unread_rooms.items():
                participants = [*USERS, *support_by_room[room].keys()]
                if user not in participants or int(unread_count) < 1:
                    raise ValueError(f"Invalid unread Talk configuration for {user} in {room}")
                writer.writerow([user, room, int(unread_count)])


def generate_notifications(spec: dict[str, Any], output_dir: Path, records: list[dict[str, Any]]) -> None:
    target = int(spec["targets"]["notifications_per_user"])
    if target != len(NOTIFICATION_BLUEPRINTS):
        raise ValueError(
            "Notification target must match the number of deterministic notification blueprints"
        )

    known_rooms = {
        *spec["talk_rooms"],
        *spec["additional_talk_rooms"],
        "Project Alpha",
    }
    known_people = set(spec["talk_users"].values())
    notification_dir = output_dir / "notifications"
    notification_dir.mkdir(parents=True, exist_ok=True)

    with (notification_dir / "notifications.tsv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        for owner in USERS:
            for index, (
                notification_key,
                actor,
                subject_template,
                file_prefix,
                room,
                message_template,
            ) in enumerate(NOTIFICATION_BLUEPRINTS):
                if actor not in known_people or room not in known_rooms:
                    raise ValueError(
                        f"Notification {notification_key} references an unknown person or Talk room"
                    )
                candidates = sorted(
                    (
                        record
                        for record in records
                        if record.get("entity_type") == "file"
                        and record.get("owner") == owner
                        and record.get("path", "").startswith(file_prefix)
                    ),
                    key=lambda record: record["path"],
                )
                if not candidates:
                    raise ValueError(
                        f"Notification {notification_key} has no related file for {owner}"
                    )
                related_file = candidates[index % len(candidates)]
                file_name = Path(related_file["path"]).name
                subject = f"{actor} {subject_template.format(file_name=file_name)}"
                message = (
                    message_template.format(room=room)
                    + f" Related file: {related_file['path']}."
                )
                object_id = f"{owner}-{notification_key}"
                writer.writerow([owner, object_id, subject, message])
                records.append(
                    {
                        "entity_type": "notification",
                        "owner": owner,
                        "object_type": "webarena_seed",
                        "object_id": object_id,
                        "actor": actor,
                        "subject": subject,
                        "message": message,
                        "related_talk_room": room,
                        "related_file": related_file["path"],
                        "related_file_sha256": related_file["sha256"],
                        "sha256": sha256_bytes(f"{subject}\n{message}".encode()),
                        "license": spec["dataset_license"],
                        "creator": DATASET_CREATOR,
                        "source": "generated",
                        "license_url": DATASET_LICENSE_URL,
                        "generator_version": GENERATOR_VERSION,
                    }
                )


def validate_xml_file(path: Path) -> None:
    ElementTree.fromstring(path.read_bytes())


def validate_generated(output_dir: Path, spec: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, Any] = {
        "files": {},
        "contacts": {},
        "calendar_events": {},
        "notifications": {user: 0 for user in USERS},
        "talk_messages": 0,
        "talk_authors": {user: 0 for user in TALK_USERS},
        "talk_threads": 0,
        "talk_replies": 0,
    }
    for owner in USERS:
        file_paths = [path for path in (output_dir / "files" / owner).rglob("*") if path.is_file()]
        counts["files"][owner] = len(file_paths)
        for path in file_paths:
            suffix = path.suffix.lower()
            if suffix in {".docx", ".xlsx", ".pptx"}:
                with zipfile.ZipFile(path) as archive:
                    if archive.testzip() is not None or "[Content_Types].xml" not in archive.namelist():
                        raise ValueError(f"Invalid OOXML package: {path}")
                    for member in archive.namelist():
                        if member.endswith(".xml"):
                            validate_xml_file_from_bytes(archive.read(member), Path(f"{path}!{member}"))
            elif suffix == ".pdf":
                payload = path.read_bytes()
                if not payload.startswith(b"%PDF-") or not payload.rstrip().endswith(b"%%EOF"):
                    raise ValueError(f"Invalid PDF: {path}")
            elif suffix == ".json":
                json.loads(path.read_text(encoding="utf-8"))
            elif suffix == ".svg":
                root = ElementTree.fromstring(path.read_bytes())
                if not root.tag.endswith("svg"):
                    raise ValueError(f"Invalid SVG plot: {path}")
        contact_paths = sorted((output_dir / "contacts" / owner).glob("*.vcf"))
        event_paths = sorted((output_dir / "calendars" / owner).glob("*.ics"))
        counts["contacts"][owner] = len(contact_paths)
        counts["calendar_events"][owner] = len(event_paths)
        for path in contact_paths:
            payload = path.read_text(encoding="utf-8")
            if not payload.startswith("BEGIN:VCARD") or "\nEND:VCARD" not in payload:
                raise ValueError(f"Invalid VCard: {path}")
        for path in event_paths:
            payload = path.read_text(encoding="utf-8")
            if not payload.startswith("BEGIN:VCALENDAR") or payload.count("BEGIN:VEVENT") != 1:
                raise ValueError(f"Invalid calendar event: {path}")

    message_keys: dict[str, str] = {}
    with (output_dir / "talk" / "messages.tsv").open(encoding="utf-8", newline="") as handle:
        for row in csv.reader(handle, delimiter="\t"):
            if len(row) != 6:
                raise ValueError(f"Invalid Talk row: {row}")
            room, author, message_key, reply_to_value, thread_title_value, message = row
            reply_to = "" if reply_to_value == "-" else reply_to_value
            thread_title = "" if thread_title_value == "-" else thread_title_value
            if author not in TALK_USERS or not message or message_key in message_keys:
                raise ValueError(f"Invalid Talk message metadata: {row[:5]}")
            if reply_to:
                if message_keys.get(reply_to) != room or thread_title:
                    raise ValueError(f"Invalid Talk reply relationship: {row[:5]}")
                counts["talk_replies"] += 1
            elif thread_title:
                counts["talk_threads"] += 1
            message_keys[message_key] = room
            counts["talk_messages"] += 1
            counts["talk_authors"][author] += 1

    with (output_dir / "talk" / "rooms.tsv").open(encoding="utf-8", newline="") as handle:
        room_rows = list(csv.reader(handle, delimiter="\t"))
    if len(room_rows) != 10 or any(len(row) != 2 for row in room_rows):
        raise ValueError("Invalid Talk room configuration")
    if any(len(row[1].split(",")) < 3 for row in room_rows if row[0] != "Project Alpha"):
        raise ValueError("Every non-canonical Talk room must contain at least three participants")

    with (output_dir / "talk" / "unread.tsv").open(encoding="utf-8", newline="") as handle:
        unread_rows = list(csv.reader(handle, delimiter="\t"))
    if len(unread_rows) < 4 or any(len(row) != 3 or int(row[2]) < 1 for row in unread_rows):
        raise ValueError("Invalid Talk unread-state configuration")

    notification_keys: set[tuple[str, str]] = set()
    with (output_dir / "notifications" / "notifications.tsv").open(
        encoding="utf-8", newline=""
    ) as handle:
        for row in csv.reader(handle, delimiter="\t"):
            if len(row) != 4:
                raise ValueError(f"Invalid notification row: {row}")
            owner, object_id, subject, message = row
            key = (owner, object_id)
            if (
                owner not in USERS
                or key in notification_keys
                or not object_id
                or len(object_id) > 64
                or not subject
                or len(subject.encode()) > 255
                or not message
                or len(message.encode()) > 4000
            ):
                raise ValueError(f"Invalid notification metadata: {row[:3]}")
            notification_keys.add(key)
            counts["notifications"][owner] += 1

    expected_files = int(spec["targets"]["files_per_user"])
    expected_contacts = int(spec["targets"]["contacts_per_user"])
    expected_events = int(spec["targets"]["calendar_events_per_user"])
    expected_notifications = int(spec["targets"]["notifications_per_user"])
    for owner in USERS:
        if counts["files"][owner] != expected_files:
            raise ValueError(f"Generated file count mismatch for {owner}: {counts['files'][owner]}")
        if counts["contacts"][owner] != expected_contacts:
            raise ValueError(f"Generated contact count mismatch for {owner}: {counts['contacts'][owner]}")
        if counts["calendar_events"][owner] != expected_events:
            raise ValueError(f"Generated event count mismatch for {owner}: {counts['calendar_events'][owner]}")
        if counts["notifications"][owner] != expected_notifications:
            raise ValueError(
                f"Generated notification count mismatch for {owner}: "
                f"{counts['notifications'][owner]}"
            )
    if counts["talk_messages"] != int(spec["targets"]["talk_messages_total"]):
        raise ValueError(f"Generated Talk count mismatch: {counts['talk_messages']}")
    expected_authors = {user: int(count) for user, count in spec["targets"]["talk_messages_by_author"].items()}
    if counts["talk_authors"] != expected_authors:
        raise ValueError(f"Generated Talk author mismatch: {counts['talk_authors']}")
    return counts


def validate_xml_file_from_bytes(payload: bytes, source: Path) -> None:
    try:
        ElementTree.fromstring(payload)
    except ElementTree.ParseError as error:
        raise ValueError(f"Invalid XML in {source}: {error}") from error


def generate_seed(spec_path: Path, media_dir: Path, output_dir: Path, asset_manifest: Path) -> dict[str, Any]:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if spec.get("version") != GENERATOR_VERSION:
        raise ValueError(f"Unsupported seed spec version: {spec.get('version')}")
    if spec.get("dataset_license") != "CC-BY-4.0":
        raise ValueError("Generated dataset license must be CC-BY-4.0")
    allowed_licenses = set(spec["allowed_asset_licenses"])
    if allowed_licenses != {"Apache-2.0", "CC-BY-4.0", "CC0-1.0"}:
        raise ValueError(f"Unexpected asset license allowlist: {allowed_licenses}")

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    records, committed_counts = load_assets(media_dir, asset_manifest, allowed_licenses, output_dir)
    real_records, real_counts = load_real_documents(
        media_dir,
        asset_manifest.with_name("real_documents.json"),
        allowed_licenses,
        output_dir,
    )
    records.extend(real_records)
    for owner in USERS:
        committed_counts[owner] += real_counts[owner]
    financial_records, financial_counts = load_financial_documents(
        spec,
        media_dir,
        asset_manifest.with_name("financial_documents.json"),
        allowed_licenses,
        output_dir,
    )
    records.extend(financial_records)
    for owner in USERS:
        committed_counts[owner] += financial_counts[owner]
    generate_documents(output_dir, records, committed_counts)
    generate_synthetic_invoices(spec, output_dir, records, committed_counts)
    generate_purchase_orders(spec, output_dir, records, committed_counts)
    generate_timesheets(spec, output_dir, records, committed_counts)
    generate_root_work_files(spec, output_dir, records, committed_counts)
    generate_bulk_files(spec, output_dir, records, committed_counts)
    generate_contacts(spec, output_dir, records)
    generate_calendars(spec, output_dir, records)
    generate_talk(spec, output_dir, records)
    generate_notifications(spec, output_dir, records)

    provenance_dir = output_dir / "provenance"
    provenance_dir.mkdir(parents=True)
    manifest_path = provenance_dir / "manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8", newline="") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    manifest_hash = sha256_file(manifest_path)
    (provenance_dir / "manifest.sha256").write_text(f"{manifest_hash}  manifest.jsonl\n", encoding="utf-8")

    counts = validate_generated(output_dir, spec)
    counts["manifest_records"] = len(records)
    counts["manifest_sha256"] = manifest_hash
    (output_dir / "counts.json").write_text(json.dumps(counts, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (output_dir / "managed_folder_counts.json").write_text(
        json.dumps(spec["managed_folder_targets"], sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True, help="Path to seed_spec.json")
    parser.add_argument("--media", type=Path, required=True, help="Path to checked-in media directory")
    parser.add_argument("--output", type=Path, required=True, help="Destination for generated artifacts")
    parser.add_argument(
        "--asset-manifest",
        type=Path,
        default=Path(__file__).with_name("assets.json"),
        help="Checked-in media provenance manifest",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    counts = generate_seed(args.spec.resolve(), args.media.resolve(), args.output.resolve(), args.asset_manifest.resolve())
    print(json.dumps(counts, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
