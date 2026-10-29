from wtforms import (
    BooleanField,
    DecimalField,
    EmailField,
    IntegerField,
    MultipleFileField,
    SelectField,
    SelectMultipleField,
    StringField,
    TelField,
    TextAreaField,
)
from wtforms.validators import Length

from uber.config import c
from uber.custom_tags import format_currency, pluralize
from uber.forms import (
    AddressForm,
    CustomValidation,
    IntSelect,
    MagForm,
    MultiCheckbox,
    NumberInputGroup,
    SelectBooleanField,
)
from uber.models import Group

__all__ = [
    "AdminGroupInfo",
    "AdminTableInfo",
    "ContactInfo",
    "GroupInfo",
    "LeaderInfo",
    "NewTableInfo",
    "TableInfo",
]


class GroupInfo(MagForm):
    name = StringField('Group Name')
    badges = IntegerField('Badges', default=0, widget=IntSelect())
    tables = DecimalField('Exhibitor Type', default=0, widget=IntSelect())

    def badges_label(self):
        return "Badges (" + format_currency(c.GROUP_PRICE) + " each)"

    def badges_desc(self):
        if c.GROUP_UPDATE_GRACE_PERIOD > 0:
            return f"You have {c.GROUP_UPDATE_GRACE_PERIOD} hour{pluralize(c.GROUP_UPDATE_GRACE_PERIOD)} "\
                   "after paying to add badges to your group without quantity restrictions. You may continue to add "\
                   "badges to your group after that, but you'll have to add at least "\
                   f"{c.MIN_GROUP_ADDITION} badges at a time."
        else:
            return "You may add badges to your group later, but you must add at least {} badges at a time.".format(
                c.MIN_GROUP_ADDITION)


class AdminGroupInfo(GroupInfo):
    guest_group_type = SelectField('Checklist Type', default=0, choices=[(0, 'N/A')] + c.GROUP_TYPE_OPTS, coerce=int)
    payment = BooleanField('Enable the W9 checklist step for this guest.')
    can_add = BooleanField('This group may purchase additional badges.')
    is_dealer = BooleanField(f'This group should be treated as {c.DEALER_INDEFINITE_TERM}.',
                             description=f"{c.DEALER_TERM.title()}s are prevented from paying until they are approved,"
                             "but may assign and purchase add-ons for badges.")
    new_badge_type = SelectField('Badge Type', choices=c.BADGE_OPTS, coerce=int)
    new_ribbons = SelectMultipleField('Badge Ribbons', choices=c.RIBBON_OPTS, coerce=int, widget=MultiCheckbox())
    cost = IntegerField('Total Group Price', widget=NumberInputGroup())
    auto_recalc = BooleanField('Automatically recalculate this number.')
    amount_paid_repr = StringField('Amount Paid', render_kw={'disabled': "disabled"})
    amount_refunded_repr = StringField('Amount Refunded', render_kw={'disabled': "disabled"})
    admin_notes = TextAreaField('Admin Notes')


class ContactInfo(AddressForm):
    email_address = EmailField('Email Address', render_kw={'placeholder': 'test@example.com'})
    phone = TelField('Phone Number',
                     render_kw={'placeholder': 'A phone number we can use to contact you during the event'})


class TableInfo(GroupInfo):
    name = StringField('Table Name')
    description = StringField('Description', description="Please keep to one sentence.")
    website = StringField('Website',
                          description="The one you want us to link on our website, or where we can view your work "
                          "to judge your application.")
    wares = TextAreaField('What do you sell?', description="Please be detailed; include a link to view your wares. "
                          "You must include links to what you sell or a portfolio otherwise you will be automatically waitlisted.")
    categories = SelectMultipleField('Categories', choices=c.DEALER_WARES_OPTS, coerce=int, widget=MultiCheckbox())
    categories_text = StringField('Other')
    selling_nsfw = SelectBooleanField("Do you plan on selling R-18/NSFW works?")
    touhou_work_percentage = SelectField(
        "How much of your work is based on Touhou?",
        choices=c.TOUHOU_WORK_PERCENTAGE_OPTS,
        coerce=int,
        default=c.ZERO,
    )
    special_needs = TextAreaField('Special Requests', description="No guarantees that we can accommodate any requests.")

    def get_non_admin_locked_fields(self, group):
        if group.is_new:
            return []
        elif group.status in c.DEALER_EDITABLE_STATUSES:
            return ['tables']

        return list(self._fields.keys())

    @property
    def dealer_discounted_badges(self):
        """
        The number of discounted badges included for the table/vendor type
        selected on this form or configured for the underlying group.
        """
        return c.DEALER_DISCOUNTED_BADGES.get(int(self.tables.data or 0), 0)

    def badges_label(self):
        if c.DEALER_DISCOUNTED_BADGES:
            return f"Badges (discounted with table, then {format_currency(c.DEALER_BADGE_PRICE)} each)"
        return f"Badges ({format_currency(c.DEALER_BADGE_PRICE)} each)"

    def badges_desc(self):
        desc = "The number of people working your table, including yourself."
        if c.DEALER_DISCOUNTED_BADGES:
            return (
                f"{desc[:-1]} (discounted badges are included with your table; "
                f"additional badges are {format_currency(c.DEALER_BADGE_PRICE)} each)."
            )
        return desc


class ExamplesUpload(MagForm):
    """
    Form used for collecting example file uploads during dealer registration.
    """
    examples = MultipleFileField('Please upload 3-5 examples of works that ' +
                                 'you plan on selling or examples of ' +
                                 'previous table displays/setups. (Max 10MB ' +
                                 'each, images only)',
                                 [Length(3, 5, '3-5 images are required.')],
                                 render_kw={
                                     'accept': 'image/*',
                                     'data-max-size': 10 * 1024 * 1024,
                                     'data-max-total-size': 50 * 1024 * 1024,
                                 })

    def get_non_admin_locked_fields(self, group: Group) -> list[str]:
        return [] if group.is_new or group.status in \
            c.DEALER_EDITABLE_STATUSES else ['examples']


class NewTableInfo(TableInfo, ExamplesUpload):
    """
    Variant of TableInfo used only on preregistration.

    This variant contains the examples file upload as file uploads are not
    permitted after initial preregistration.
    """


class AdminTableInfo(TableInfo, AdminGroupInfo):
    status = SelectField('Status', choices=c.DEALER_STATUS_OPTS, coerce=int)
    shared_with_name = StringField(
        'Shared With', description=f"The {c.DEALER_APP_TERM} this {c.DEALER_APP_TERM} is sharing a table with.")
    convert_badges = BooleanField("Convert this group's badges to individual badges.")

    def can_add_label(self):
        if c.MAX_DEALERS:
            return "This {} can add up to {} badges.".format(c.DEALER_TERM, c.MAX_DEALERS)
        else:
            return "This {} can add badges up to their personal maximum.".format(c.DEALER_TERM)


class LeaderInfo(MagForm):
    field_validation = CustomValidation()

    leader_first_name = StringField('First Name')
    leader_last_name = StringField('Last Name')
    leader_email = EmailField('Email Address', render_kw={'placeholder': 'test@example.com'})
    leader_cellphone = TelField('Phone Number')
