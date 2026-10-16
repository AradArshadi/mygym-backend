from html import escape
from pathlib import PurePosixPath

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from apps.gyms.models import GymImage


class Command(BaseCommand):
    help = 'Restore missing legacy demo SVG covers; never overwrite uploads or change database rows.'

    def handle(self, *args, **options):
        restored = 0
        for photo in GymImage.objects.filter(source='placeholder', external_url='').select_related('gym'):
            if not photo.image:
                continue
            name = photo.image.name
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name or not name.startswith('gyms/generated/') or path.suffix != '.svg':
                continue
            storage = photo.image.storage
            if storage.exists(name):
                continue
            title = escape(photo.gym.name)
            svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="720" viewBox="0 0 1200 720" role="img" aria-labelledby="title desc">
<title id="title">{title} - demo illustration</title><desc id="desc">Illustrated gym equipment. A venue photo has not been uploaded.</desc>
<defs><linearGradient id="bg" x2="1" y2="1"><stop stop-color="#303e48"/><stop offset="1" stop-color="#151c25"/></linearGradient><radialGradient id="glow"><stop stop-color="#e8ca84" stop-opacity=".3"/><stop offset="1" stop-color="#e8ca84" stop-opacity="0"/></radialGradient></defs>
<path fill="url(#bg)" d="M0 0h1200v720H0z"/><ellipse fill="url(#glow)" cx="880" cy="150" rx="500" ry="400"/>
<g stroke="#ffffff" stroke-opacity=".08" fill="none"><path d="M0 580h1200M0 640h1200M200 500 0 720M450 500 350 720M750 500 850 720M1000 500l200 220"/><path d="M120 80v420M420 80v420M780 80v420M1080 80v420"/></g>
<g fill="#1b252f" stroke="#c7b58b" stroke-width="10" stroke-linejoin="round"><path d="M315 530V180h390v350M270 530h90M660 530h90" fill="none"/><path d="M270 260h480" fill="none"/><rect x="295" y="215" width="30" height="90" rx="8"/><rect x="695" y="215" width="30" height="90" rx="8"/><path d="m465 425-55 100m185-100 60 100" fill="none"/><rect x="405" y="400" width="210" height="28" rx="12"/>
<path d="m860 485 125-95" fill="none" stroke-width="16"/><rect x="822" y="462" width="48" height="80" rx="10" transform="rotate(-37 846 502)"/><rect x="973" y="350" width="48" height="80" rx="10" transform="rotate(-37 997 390)"/></g>
<g font-family="system-ui,sans-serif" fill="#efe9dc"><text x="65" y="90" font-size="32" font-weight="700">myGym</text><rect x="65" y="598" width="520" height="52" rx="26" fill="#131a23"/><text x="90" y="632" font-size="21">Demo illustration · Venue photo coming soon</text></g></svg>'''
            saved = storage.save(name, ContentFile(svg.encode('utf-8')))
            if saved != name:
                self.stderr.write(f'Storage selected a different name for {name}; record was not changed.')
            else:
                restored += 1
        self.stdout.write(self.style.SUCCESS(f'Restored {restored} missing demo cover(s). No database records changed.'))
