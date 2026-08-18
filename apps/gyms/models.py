from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Facility(models.Model):
    name = models.CharField(max_length=80, unique=True)
    icon = models.CharField(max_length=40, blank=True)

    class Meta:
        verbose_name_plural = 'Facilities'

    def __str__(self):
        return self.name


class ImportBatch(models.Model):
    """Groups imported third-party data so demo/imported records can be audited or wiped safely."""

    source = models.CharField(max_length=50, default='openstreetmap')
    city = models.CharField(max_length=100)
    country = models.CharField(max_length=100, blank=True)
    query = models.TextField(blank=True)
    total_found = models.PositiveIntegerField(default=0)
    total_created = models.PositiveIntegerField(default=0)
    total_updated = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.source} import for {self.city} ({self.created_at:%Y-%m-%d %H:%M})'


class Gym(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending approval'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_gyms')
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    description = models.TextField()
    city = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    website = models.URLField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    facilities = models.ManyToManyField(Facility, blank=True, related_name='gyms')
    starting_price = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # Import/claim pipeline fields. These let us safely remove imported data without touching real owner-created gyms.
    is_imported = models.BooleanField(default=False, db_index=True)
    is_claimed = models.BooleanField(default=False, db_index=True)
    source = models.CharField(max_length=50, blank=True, db_index=True)
    external_id = models.CharField(max_length=255, blank=True, db_index=True)
    import_batch = models.ForeignKey(ImportBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='gyms')
    imported_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return f'/gyms/{self.slug}/'

    @property
    def cover_image(self):
        cover = self.images.filter(is_cover=True).first()
        if cover:
            return cover
        return self.images.first()

    @property
    def gallery_images(self):
        return self.images.filter(is_cover=False)

    def mark_imported(self, source, external_id, batch=None):
        self.is_imported = True
        self.is_claimed = False
        self.source = source
        self.external_id = external_id
        self.import_batch = batch
        self.imported_at = timezone.now()


class GymImage(models.Model):
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='gyms/', blank=True, null=True)
    external_url = models.URLField(blank=True, help_text='Optional externally hosted image URL for imported/demo listings.')
    source = models.CharField(max_length=50, blank=True, help_text='Image source, e.g. owner_upload, placeholder, google_places.')
    credit = models.CharField(max_length=160, blank=True, help_text='Optional attribution/credit for external photos.')
    remote_id = models.CharField(max_length=80, blank=True, help_text='Remote image identifier returned by the hosting provider.')
    remote_delete_url = models.URLField(blank=True, help_text='Provider cleanup URL. Keep private; do not expose via public API.')
    remote_width = models.PositiveIntegerField(null=True, blank=True)
    remote_height = models.PositiveIntegerField(null=True, blank=True)
    remote_size = models.PositiveIntegerField(null=True, blank=True, help_text='Remote image size in bytes.')
    alt_text = models.CharField(max_length=160, blank=True)
    is_cover = models.BooleanField(default=False)

    @property
    def image_url(self):
        # New uploads are remote-first. The ImageField remains only for backward
        # compatibility while old local files are migrated.
        if self.external_url:
            return self.external_url
        if self.image:
            try:
                return self.image.url
            except Exception:
                return ''
        return ''

    def __str__(self):
        return self.alt_text or f'Image for {self.gym.name}'


class MembershipPlan(models.Model):
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, related_name='plans')
    title = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    duration_days = models.PositiveIntegerField()
    is_trial = models.BooleanField(default=False)

    class Meta:
        ordering = ['price']

    def __str__(self):
        return f'{self.gym.name} - {self.title}'


class TrainerProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trainer_profile')
    gym = models.ForeignKey(Gym, on_delete=models.CASCADE, related_name='trainers')
    bio = models.TextField()
    specialties = models.CharField(max_length=255, help_text='Comma-separated: Strength, Boxing, Yoga')
    hourly_rate = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)], null=True, blank=True)
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return self.user.get_full_name() or self.user.username
