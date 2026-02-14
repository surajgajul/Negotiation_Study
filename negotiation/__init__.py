from otree.api import *
import json
from datetime import datetime
from services.otree_randomization import OTreeRandomization
from services.orchestrator import Orchestrator
from services.parsing import detect_acceptance, extract_first_int
from services.session_logger import SessionLogger
from services.audit_log import AuditLogger


doc = """
Human-AI Negotiation Study
Participants negotiate prices with AI agents across multiple rounds.
"""


class C(BaseConstants):
    NAME_IN_URL = 'negotiation'
    PLAYERS_PER_GROUP = None  # Single player negotiating with AI (None means all players in subsession)
    NUM_ROUNDS = 8  # 4 rounds × 2 blocks


class Subsession(BaseSubsession):
    """Round-level configuration"""
    round_in_block = models.IntegerField(initial=0)  # Which round within the block (1-4)
    reflection_on = models.BooleanField(initial=False)  # Whether reflection is enabled
    block_number = models.IntegerField(initial=0)  # Which block (1 or 2)
    initiator = models.StringField(initial="human")  # "human" or "ai"
    seed_round = models.IntegerField(initial=0)  # Deterministic seed for this round

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Initialization deferred to SessionStart.before_next_page()
        # where player randomization fields are properly set

    def initialize_round(self):
        """Initialize round configuration based on participant randomization"""
        if len(self.get_players()) == 0:
            return

        player = self.get_players()[0]
        round1_player = player.in_round(1)

        # Lazily assign randomization if not done yet
        if round1_player.sequence_id == 0:
            randomizer = OTreeRandomization()
            assignment = randomizer.assign_participant(round1_player.participant.code)
            round1_player.sequence_id = assignment["sequence_id"]
            round1_player.block_order = assignment["block_order"]
            round1_player.session_seed = assignment["session_seed"]
            print(f">>> Lazy-assigned participant {round1_player.participant.code} -> seq={round1_player.sequence_id}, order={round1_player.block_order}, seed={round1_player.session_seed}")
            AuditLogger.log(
                event_type="participant_assignment",
                participant_code=round1_player.participant.code,
                payload={
                    "sequence_id": assignment["sequence_id"],
                    "block_order": assignment["block_order"],
                    "session_seed": assignment["session_seed"],
                },
            )

        randomizer = OTreeRandomization()
        config = randomizer.get_round_config(
            round_num=self.round_number,
            sequence_id=round1_player.sequence_id,
            block_order=round1_player.block_order,
            session_seed=round1_player.session_seed,
        )

        # Apply config to subsession
        self.round_in_block = config["round_in_block"]
        self.reflection_on = config["reflection_on"]
        self.block_number = config["block_number"]
        self.seed_round = config["seed_round"]

        # Set initiator based on round number
        self._set_initiator()
        print(f">>> Subsession {self.round_number} initialized: reflection={self.reflection_on}, initiator={self.initiator}")

    def _set_initiator(self):
        """Set initiator based on round number: odd=ai, even=human"""
        is_odd = self.round_number % 2 == 1
        self.initiator = "ai" if is_odd else "human"
        print(f">>> Round {self.round_number}: is_odd={is_odd}, initiator={self.initiator}")


class Group(BaseGroup):
    """Group fields for negotiation state"""
    # Conversation history stored as JSON
    messages = models.LongStringField(default='[]')  # List of {"sender": "human"/"ai", "text": "...", "offer": int}

    # Turn tracking
    turn_count = models.IntegerField(initial=0)

    # Last offer for context
    last_human_offer = models.IntegerField(blank=True, null=True)
    last_ai_offer = models.IntegerField(blank=True, null=True)

    # AI response caching
    last_ai_message = models.LongStringField(blank=True)

    def get_messages(self):
        """Parse message history"""
        try:
            return json.loads(self.messages)
        except:
            return []

    def add_message(self, sender, text, offer=None):
        """Add a message to history"""
        messages = self.get_messages()
        messages.append({
            "sender": sender,
            "text": text,
            "offer": offer,
            "timestamp": datetime.now().isoformat()
        })
        self.messages = json.dumps(messages)


class Player(BasePlayer):
    """Player-level data"""

    def set_player_role(self):
        """Assign player role - called after player is fully initialized"""
        print(f">>> Player.set_player_role() called for player {self.id}, round {self.round_number}")

        # For rounds > 1, copy randomization fields from round 1
        if self.round_number > 1:
            round1_player = self.in_round(1)
            self.sequence_id = round1_player.sequence_id
            self.block_order = round1_player.block_order
            self.session_seed = round1_player.session_seed
            print(f">>> Player {self.id} round {self.round_number}: copied from round 1 - seq={self.sequence_id}, order={self.block_order}")

        # Assign role for this round
        try:
            randomizer = OTreeRandomization()
            config = randomizer.get_round_config(
                round_num=self.round_number,
                sequence_id=self.sequence_id,
                block_order=self.block_order,
                session_seed=self.session_seed,
            )
            self.player_role = config["player_role"]
            print(f">>> Player {self.id} round {self.round_number}: role={self.player_role}, reflection={config['reflection_on']}")
        except Exception as e:
            print(f">>> ERROR assigning role: {e}")
            import traceback
            traceback.print_exc()
            self.player_role = 'supplier'

    # Randomization fields (assigned at session start)
    sequence_id = models.IntegerField(initial=0)  # Within-block sequence (1-8)
    block_order = models.StringField(initial="OffOn")  # "OffOn" or "OnOff"
    session_seed = models.IntegerField(initial=0)  # Session seed for deterministic randomization

    # Role assignment for current round - assign based on round number for testing
    player_role = models.StringField(choices=['buyer', 'supplier', ''], blank=True, initial='')

    def get_role(self):
        """Get role based on round number"""
        # Alternate roles each round: round 1,3,5,7 = buyer, round 2,4,6,8 = supplier
        if hasattr(self, 'round_number') and self.round_number:
            return 'buyer' if self.round_number % 2 == 1 else 'supplier'
        return 'supplier'

    # Round outcomes
    final_price = models.IntegerField(blank=True, null=True)  # Deal price if reached
    agreement_reached = models.BooleanField(initial=False)
    negotiation_complete = models.BooleanField(initial=False)  # Flag for page flow control

    # Negotiation round interaction
    human_message = models.LongStringField(blank=True)  # Human's message
    human_offer = models.IntegerField(blank=True, null=True)  # Human's offer
    human_action = models.StringField(choices=['counter', 'accept'], blank=True)  # Action type
    ai_message = models.LongStringField(blank=True)  # AI's response
    ai_offer = models.IntegerField(blank=True, null=True)  # AI's offer

    # Survey responses
    negotiation_experience = models.IntegerField(blank=True, null=True, choices=[1, 2, 3, 4, 5, 6, 7])
    ai_familiarity = models.IntegerField(blank=True, null=True, choices=[1, 2, 3, 4, 5, 6, 7])
    ai_ability_rating = models.IntegerField(blank=True, null=True, choices=[1, 2, 3, 4, 5, 6, 7])
    behavior_patterns = models.LongStringField(blank=True)
    realism_rating = models.IntegerField(blank=True, null=True, choices=[1, 2, 3, 4, 5, 6, 7])
    additional_comments = models.LongStringField(blank=True)

    # Pre-survey
    age = models.IntegerField(blank=True, null=True)
    gender = models.StringField(choices=['Male', 'Female', 'Other', 'Rather not say'], blank=True)


# PAGES
class SessionStart(Page):
    """Welcome page on session start (only shows round 1)"""
    def is_displayed(self):
        return self.round_number == 1

    def before_next_page(self, timeout_happened=False):
        """Assign participant randomization on session start"""
        # In oTree, 'self' in page methods is the player
        randomizer = OTreeRandomization()
        assignment = randomizer.assign_participant(self.participant.code)
        self.sequence_id = assignment["sequence_id"]
        self.block_order = assignment["block_order"]
        self.session_seed = assignment["session_seed"]
        print(f">>> SessionStart: Assigned participant {self.participant.code} -> seq={self.sequence_id}, order={self.block_order}, seed={self.session_seed}")


class Introduction(Page):
    """Welcome and instructions"""
    def is_displayed(self):
        return self.round_number == 1


class PreSurvey(Page):
    """Pre-negotiation survey"""
    form_model = 'player'
    form_fields = ['age', 'gender', 'negotiation_experience', 'ai_familiarity']

    def is_displayed(self):
        return self.round_number == 1

    def error_message(self, values):
        """Validate survey responses"""
        errors = {}

        if values.get('age'):
            age = values['age']
            if age < 18 or age > 120:
                errors['age'] = 'Please enter a valid age (18-120)'

        if not values.get('gender'):
            errors['gender'] = 'Please select a gender'

        if not values.get('negotiation_experience'):
            errors['negotiation_experience'] = 'Please rate your negotiation experience'

        if not values.get('ai_familiarity'):
            errors['ai_familiarity'] = 'Please rate your AI familiarity'

        return errors if errors else None


class RoundInstructions(Page):
    """Show role for this round"""
    def vars_for_template(self):
        """Pass round info to template"""
        # Use the get_role() method if player_role is not set
        role = self.player_role if self.player_role else self.get_role()

        print(f"\n=== DEBUG RoundInstructions ===")
        print(f"Round: {self.subsession.round_number}")
        print(f"Player ID: {self.id}")
        print(f"player_role from DB: {repr(self.player_role)}")
        print(f"role (using get_role): {repr(role)}")
        print(f"=== END DEBUG ===\n")

        return {
            'round_number': self.subsession.round_number,
            'player_role': role,
        }



class Negotiation(Page):
    """Main negotiation page - handle message exchange with AI

    This page loops on itself until agreement is reached or max turns exceeded.
    Each submission adds messages to conversation history and reloads the page.
    """
    form_model = 'player'
    form_fields = ['human_message', 'human_offer', 'human_action']

    # def form_validation(self, cleaned_data):
    #     """Validate form based on action (accept or counter)"""
    #     # Get action from button click (oTree captures button value automatically)
    #     action = cleaned_data.get('human_action', 'counter')
    #     message = cleaned_data.get('human_message', '').strip()
    #     offer = cleaned_data.get('human_offer')

    #     print(f">>> form_validation: action={action}, message={repr(message)}, offer={offer}")

    #     # If accept action, skip validation - allow empty fields
    #     if action == 'accept':
    #         print(f">>> form_validation: ACCEPT button clicked - skipping field validation")
    #         return

    #     # If counter action, validate both fields are required
    #     print(f">>> form_validation: COUNTER button clicked - validating both fields required")

    #     if not message:
    #         self.form.add_error('human_message', 'Please enter a message')

    #     if offer is None:
    #         self.form.add_error('human_offer', 'Please enter an offer')
    def error_message(self, values):
        action = values.get('human_action', 'counter')
        message = values.get('human_message', '').strip()
        offer = values.get('human_offer')

        print(f">>> error_message: action={action}, message={repr(message)}, offer={offer}")

        # If accept → no validation
        if action == 'accept':
            return

        # If counter → validate both required and offer is in range
        if not message:
            return 'Please enter a message when making a counter-offer.'

        if offer is None:
            return 'Please enter an offer when making a counter-offer.'

        # Validate offer is within valid range
        # Determine valid range based on round number (alternating)
        round_num = self.round_number
        if round_num % 2 == 1:  # Odd rounds
            valid_range = [1, 99]
        else:  # Even rounds
            valid_range = [31, 200]

        if offer < valid_range[0] or offer > valid_range[1]:
            return f'Offer must be between ${valid_range[0]} and ${valid_range[1]}.'

    def is_displayed(self):
        """Show Negotiation page only while negotiation is in progress"""
        return not self.negotiation_complete

    def vars_for_template(self):
        """Prepare context for template"""
        # Ensure subsession is initialized with correct randomization values
        self.subsession.initialize_round()

        messages = self.group.get_messages()

        # Get settings
        settings = self.session.config or {}

        # Get player role - use get_role() if not set in DB
        player_role = self.player_role if self.player_role else self.get_role()

        # Alternate ranges between rounds: odd rounds use [1, 99], even rounds use [31, 200]
        # BOTH buyer and supplier use the SAME range in each round
        round_num = self.round_number
        if round_num % 2 == 1:  # Odd rounds (1, 3, 5, 7)
            valid_range = [1, 99]
        else:  # Even rounds (2, 4, 6, 8)
            valid_range = [31, 200]

        # Role label
        if player_role == 'buyer':
            role_label = "BUYER"
        else:
            role_label = "SUPPLIER"

        # Initialize logger for this session
        logger = SessionLogger(self.session.code)

        # Log round start if first time
        if not messages:
            logger.log_round_start(
                round_num=self.subsession.round_number,
                player_id=self.id,
                role=player_role,
                reflection_on=self.subsession.reflection_on,
                initiator=self.subsession.initiator
            )
            AuditLogger.log(
                event_type="round_init",
                session_code=self.session.code,
                participant_code=self.participant.code,
                round_number=self.subsession.round_number,
                payload={
                    "reflection_on": self.subsession.reflection_on,
                    "player_role": player_role,
                    "initiator": self.subsession.initiator,
                    "block_number": self.subsession.block_number,
                    "round_in_block": self.subsession.round_in_block,
                    "seed_round": self.subsession.seed_round,
                    "bounds": valid_range,
                },
            )

        # Generate initial AI message if AI goes first and no messages yet
        print(f"=== DEBUG AI INIT === messages: {len(messages)}, initiator: {self.subsession.initiator}")
        if not messages and self.subsession.initiator == 'ai':
            print(f">>> Generating initial AI message (player role: {player_role})")
            try:
                ai_role = 'supplier' if player_role == 'buyer' else 'buyer'
                ai_bounds = valid_range
                print(f">>> AI role: {ai_role}, bounds: {ai_bounds}, reflection: {self.subsession.reflection_on}")

                orchestrator = Orchestrator()
                print(f">>> Orchestrator created")
                ai_response = orchestrator.respond(
                    role=ai_role,
                    reflection=self.subsession.reflection_on,
                    conversation_history=[],
                    last_offer=None,
                    seed=self.subsession.seed_round,
                    bounds=tuple(ai_bounds),
                    session_code=self.session.code,
                    round_number=self.subsession.round_number,
                    participant_code=self.participant.code,
                )
                print(f">>> Got AI response: {ai_response}")

                self.group.add_message(
                    'ai',
                    ai_response['content'],
                    ai_response.get('numeric_offer')
                )
                # Log AI message
                logger.log_message(
                    round_num=self.subsession.round_number,
                    sender='ai',
                    text=ai_response['content'],
                    offer=ai_response.get('numeric_offer')
                )
                AuditLogger.log(
                    event_type="ai_message",
                    session_code=self.session.code,
                    participant_code=self.participant.code,
                    round_number=self.subsession.round_number,
                    payload={
                        "context": "initial_ai_turn",
                        "text": ai_response['content'],
                        "numeric_offer": ai_response.get('numeric_offer'),
                        "reflection_note": ai_response.get('reflection_note'),
                    },
                )
                messages = self.group.get_messages()
                print(f">>> Added message, now have {len(messages)} messages")
            except Exception as e:
                import traceback
                print(f"ERROR generating initial AI message: {str(e)}")
                print(f"Traceback: {traceback.format_exc()}")
                AuditLogger.log(
                    event_type="error",
                    session_code=self.session.code,
                    participant_code=self.participant.code,
                    round_number=self.subsession.round_number,
                    payload={
                        "context": "initial_ai_message",
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                    },
                )
                error_text = f"[Error generating opening offer: {str(e)[:80]}]"
                self.group.add_message(
                    'ai',
                    error_text,
                    None
                )
                logger.log_message(
                    round_num=self.subsession.round_number,
                    sender='ai',
                    text=error_text,
                    offer=None
                )
                messages = self.group.get_messages()

        # Check if negotiation is complete
        max_turns = settings.get('max_turns_per_side', 6)
        negotiation_complete = False
        status_message = ''
        print(f"=== NEGOTIATION CHECK === messages: {len(messages)}, max_turns: {max_turns}")

        # Check for agreement (someone said "accept" or "I accept")
        agreement_detected = False
        for msg in messages:
            if 'accept' in msg.get('text', '').lower():
                agreement_detected = True
                break

        if agreement_detected:
            negotiation_complete = True
            # Find the last offer
            final_offer = None
            for msg in reversed(messages):
                if msg.get('offer'):
                    final_offer = msg.get('offer')
                    break
            status_message = f'Agreement reached at ${final_offer}! Click "Next Round" to continue.'
            print(f">>> Agreement detected")
        elif len(messages) >= max_turns * 2:
            negotiation_complete = True
            status_message = 'Maximum turns reached. Click "Next Round" to continue.'
            print(f">>> Max turns reached: {len(messages)} >= {max_turns * 2}")

        # Calculate turn information (count only human messages)
        human_turns = len([m for m in messages if m.get('sender') == 'human'])
        turns_left = max(0, max_turns - human_turns)

        return {
            'round_number': self.subsession.round_number,
            'messages': messages,
            'player_role': player_role,
            'role_label': role_label,
            'valid_min': valid_range[0],
            'valid_max': valid_range[1],
            'subsession_reflection': self.subsession.reflection_on,
            'subsession_initiator': self.subsession.initiator,
            'negotiation_complete': negotiation_complete,
            'status_message': status_message,
            'human_turns': human_turns,
            'max_turns': max_turns,
            'turns_left': turns_left,
        }

    def before_next_page(self, timeout_happened=False):
        """Handle message submission: store human msg, get AI response, stay on page"""
        print(f"\n=== BEFORE_NEXT_PAGE START === negotiation_complete={self.negotiation_complete}")

        # Get action from button click (oTree captures button value automatically)
        action = self.human_action if self.human_action else 'counter'

        # Get message and offer safely
        human_message = self.human_message if self.human_message else ''
        human_offer = self.field_maybe_none('human_offer')

        print(f">>> action: {action}, message: {repr(human_message)}, offer: {human_offer}")

        # Initialize logger
        logger = SessionLogger(self.session.code)

        # Handle accept action - mark negotiation as complete and move to next round
        if action == 'accept':
            print(f">>> Handling ACCEPT action - negotiation complete")
            # Get the last AI offer from messages
            messages = self.group.get_messages()
            last_offer = None
            if messages:
                for msg in reversed(messages):
                    if msg.get('offer') is not None:
                        last_offer = msg.get('offer')
                        break

            print(f">>> Accepting offer: ${last_offer}")
            self.group.add_message(
                'human',
                f"I accept ${last_offer}",
                last_offer
            )
            logger.log_message(
                round_num=self.subsession.round_number,
                sender='human',
                text=f"I accept ${last_offer}",
                offer=last_offer
            )
            # Mark negotiation as complete so page moves to RoundResults
            self.negotiation_complete = True
            self.agreement_reached = True
            self.final_price = last_offer
            AuditLogger.log(
                event_type="human_submit",
                session_code=self.session.code,
                participant_code=self.participant.code,
                round_number=self.subsession.round_number,
                payload={"action": "accept", "accepted_offer": last_offer},
            )
            print(f">>> Negotiation marked complete, moving to next page")
            return

        # For counter action - get message and offer safely
        human_message = self.human_message if self.human_message else ''
        human_offer = self.field_maybe_none('human_offer')

        print(f"human_message: {repr(human_message)}")
        print(f"human_offer: {human_offer}")

        # Only process counter if human submitted something
        if not (human_message and human_offer is not None):
            print(f">>> Skipping: message or offer missing")
            return

        print(f">>> Processing COUNTER action")

        # Store in player fields for record
        self.human_message = human_message
        self.human_offer = human_offer

        # Add human message to history
        self.group.add_message(
            'human',
            human_message,
            human_offer
        )
        # Log human message
        logger.log_message(
            round_num=self.subsession.round_number,
            sender='human',
            text=human_message,
            offer=human_offer
        )
        AuditLogger.log(
            event_type="human_submit",
            session_code=self.session.code,
            participant_code=self.participant.code,
            round_number=self.subsession.round_number,
            payload={"action": "counter", "message": human_message, "offer": human_offer},
        )

        # Get conversation history for context (include offer amounts so LLM sees all numbers)
        messages_list = self.group.get_messages()
        conversation_text = []
        for m in messages_list:
            entry = f"{m['sender']}: {m['text']}"
            if m.get('offer') and str(m['offer']) not in m.get('text', ''):
                entry += f" [Offer: ${m['offer']}]"
            conversation_text.append(entry)

        # Get price ranges - alternate between rounds, BOTH buyer and supplier use SAME range
        round_num = self.round_number
        if round_num % 2 == 1:  # Odd rounds (1, 3, 5, 7)
            valid_range = (1, 99)
        else:  # Even rounds (2, 4, 6, 8)
            valid_range = (31, 200)

        # Both buyer and supplier use the same range
        buyer_range = valid_range
        supplier_range = valid_range

        # Determine AI role (opposite of human)
        player_role = self.player_role if self.player_role else self.get_role()
        ai_role = 'supplier' if player_role == 'buyer' else 'buyer'

        # AI uses the same range as its role would use (which is now the same for all)
        ai_bounds = valid_range

        # Get AI response via orchestrator
        print(f">>> Getting AI response (role: {ai_role}, bounds: {ai_bounds})")
        try:
            orchestrator = Orchestrator()
            print(f">>> Orchestrator created")
            ai_response = orchestrator.respond(
                role=ai_role,
                reflection=self.subsession.reflection_on,
                conversation_history=conversation_text,
                last_offer=human_offer,
                seed=self.subsession.seed_round,
                bounds=ai_bounds,
                session_code=self.session.code,
                round_number=self.subsession.round_number,
                participant_code=self.participant.code,
            )
            print(f">>> Got AI response: {ai_response}")

            # Add AI response to history
            self.group.add_message(
                'ai',
                ai_response['content'],
                ai_response.get('numeric_offer')
            )
            print(f">>> Added AI message to group")

            # Log AI response
            logger.log_message(
                round_num=self.subsession.round_number,
                sender='ai',
                text=ai_response['content'],
                offer=ai_response.get('numeric_offer')
            )
            AuditLogger.log(
                event_type="ai_message",
                session_code=self.session.code,
                participant_code=self.participant.code,
                round_number=self.subsession.round_number,
                payload={
                    "context": "counter_response",
                    "text": ai_response['content'],
                    "numeric_offer": ai_response.get('numeric_offer'),
                    "reflection_note": ai_response.get('reflection_note'),
                },
            )
            print(f">>> Logged AI message")

        except Exception as e:
            # Add error message if LLM call fails
            import traceback
            print(f">>> ERROR: {str(e)}")
            print(traceback.format_exc())
            error_msg = f"[Error: {str(e)[:100]}]"
            print(f"ERROR in orchestrator.respond: {error_msg}")
            print(f"Traceback: {traceback.format_exc()}")
            self.group.add_message(
                'ai',
                error_msg,
                None
            )
            # Log error
            logger.log_message(
                round_num=self.subsession.round_number,
                sender='ai',
                text=error_msg,
                offer=None
            )
            AuditLogger.log(
                event_type="error",
                session_code=self.session.code,
                participant_code=self.participant.code,
                round_number=self.subsession.round_number,
                payload={
                    "context": "ai_counter_response",
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                },
            )

        # Check if negotiation is now complete and set flag
        messages = self.group.get_messages()
        max_turns = self.session.config.get('max_turns_per_side', 6)

        agreement_detected = False
        for msg in messages:
            if 'accept' in msg.get('text', '').lower():
                agreement_detected = True
                break

        if agreement_detected or len(messages) >= max_turns * 2:
            self.negotiation_complete = True
            AuditLogger.log(
                event_type="negotiation_complete",
                session_code=self.session.code,
                participant_code=self.participant.code,
                round_number=self.subsession.round_number,
                payload={
                    "reason": "agreement" if agreement_detected else "max_turns",
                    "total_messages": len(messages),
                },
            )
            print(f">>> Negotiation marked complete")
        else:
            # Clear form fields for next submission
            self.human_message = ''
            self.human_offer = None
            print(f">>> BEFORE_NEXT_PAGE END - continuing negotiation")



class RoundResults(Page):
    """Show round outcome - only displayed when negotiation is complete"""

    def is_displayed(self):
        """Only show results when negotiation is complete"""
        return self.negotiation_complete

    def vars_for_template(self):
        """Display round results"""
        # Get messages to determine final price
        messages = self.group.get_messages()
        final_price = 'N/A'
        agreement_reached = False

        if messages:
            last_msg = messages[-1]
            if 'accept' in last_msg.get('text', '').lower():
                agreement_reached = True
                final_price = last_msg.get('offer', 'N/A')

        # Log round completion
        logger = SessionLogger(self.session.code)
        logger.log_round_complete(
            round_num=self.subsession.round_number,
            agreement_reached=agreement_reached,
            final_price=final_price if isinstance(final_price, int) else None
        )
        AuditLogger.log(
            event_type="round_complete",
            session_code=self.session.code,
            participant_code=self.participant.code,
            round_number=self.subsession.round_number,
            payload={
                "agreement_reached": agreement_reached,
                "final_price": final_price if isinstance(final_price, int) else None,
                "total_messages": len(messages),
            },
        )

        return {
            'round_number': self.subsession.round_number,
            'agreement_reached': agreement_reached,
            'final_price': final_price,
            'player_role': self.player_role,
        }


class PostSurvey(Page):
    """Post-study survey"""
    form_model = 'player'
    form_fields = ['ai_ability_rating', 'behavior_patterns', 'realism_rating', 'additional_comments']

    def is_displayed(self):
        return self.round_number == C.NUM_ROUNDS

    def error_message(self, values):
        """Validate post-survey responses"""
        errors = {}

        

        if not values.get('ai_ability_rating'):
            errors['ai_ability_rating'] = 'Please rate the AI\'s negotiation ability'

        if not values.get('realism_rating'):
            errors['realism_rating'] = 'Please rate how realistic the negotiations felt'

        return errors if errors else None


class FinalResults(Page):
    """Study completion"""
    def is_displayed(self):
        return self.round_number == C.NUM_ROUNDS


page_sequence = [
    Introduction,  # Welcome (round 1 only)
    PreSurvey,  # Pre-survey (round 1 only)
    RoundInstructions,  # Show role (all rounds)
    Negotiation,  # Negotiate - looping up to 6 times
    Negotiation,
    Negotiation,
    Negotiation,
    Negotiation,
    Negotiation,
    RoundResults,  # Show outcome (all rounds)
    PostSurvey,  # Post-survey (round 8 only)
    FinalResults,  # Completion (round 8 only)
]
