import os
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.contrib.contenttypes.models import ContentType


class Command(BaseCommand):
    args = "<app.model> <field>"
    help = "Re-generates thumbnails for all instances of the given model, for the given field."

    def add_arguments(self, parser):
        parser.add_argument(
            "model_name", nargs=1, help='The model, such as "learn.Series"'
        )
        parser.add_argument(
            "field_name", nargs=1, help='The field name, such as "image"'
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force regeneration of all thumbnails, even if they exist"
        )

    def handle(self, *args, **options):
        self.model_name = options["model_name"][0]
        self.field_name = options["field_name"][0]
        self.force_regen = options.get("force", False)

        self.validate_input()
        self.parse_input()
        self.regenerate_thumbs()

    def validate_input(self):
        if "." not in self.model_name:
            raise CommandError("The first argument must be in the format of: app.model")

    def parse_input(self):
        """
        Go through the user input, get/validate some important values.
        """
        app_split = self.model_name.split(".")
        app = app_split[0]
        model_name = app_split[1].lower()

        try:
            self.model = ContentType.objects.get(app_label=app, model=model_name)
            self.model = self.model.model_class()
        except ContentType.DoesNotExist:
            raise CommandError(
                "There is no app/model combination: %s" % self.model_name
            )

        # String field name to re-generate.
        self.field = self.field_name

    def get_missing_thumbnails(self, file_field):
        """
        Check which thumbnail variations are missing for a given file field.
        Returns a list of missing thumbnail names.
        """
        if not hasattr(file_field, 'field') or not hasattr(file_field.field, 'thumbs'):
            return []

        missing_thumbs = []

        for thumb in file_field.field.thumbs:
            thumb_name, thumb_options = thumb
            thumb_filename = file_field._calc_thumb_filename(thumb_name)

            print(f"checking thumb - ${thumb_filename}")

            # Check if the thumbnail file exists in storage


            if not file_field.storage.exists(thumb_filename):
                print(f"\tmissing thumb - ${thumb_filename}")
                missing_thumbs.append(thumb_name)
            else:
                print(f"\tthumb found - ${thumb_filename}")

        return missing_thumbs

    def needs_regeneration(self, file_field):
        """
        Determine if thumbnails need to be regenerated for this file field.
        Returns True if any thumbnails are missing or if force mode is enabled.
        """
        if self.force_regen:
            return True

        missing_thumbs = self.get_missing_thumbnails(file_field)
        return len(missing_thumbs) > 0

    def regenerate_thumbs(self):
        """
        Handle re-generating the thumbnails. Only regenerates when thumbnails
        are missing or when --force is used.
        """
        Model = self.model
        instances = Model.objects.all()
        num_instances = instances.count()

        processed_count = 0
        skipped_no_file = 0
        skipped_exists = 0
        error_count = 0

        # Filenames are keys in here, to help avoid re-genning something that
        # we have already done in this run.
        regen_tracker = {}

        counter = 1
        for instance in instances:
            file = getattr(instance, self.field)
            if not file:
                print(
                    "(%d/%d) ID: %d -- Skipped -- No file"
                    % (counter, num_instances, instance.id)
                )
                skipped_no_file += 1
                counter += 1
                continue

            file_name = os.path.basename(file.name)

            if file_name in regen_tracker:
                print(
                    "(%d/%d) ID: %d -- Skipped -- Already processed %s"
                    % (counter, num_instances, instance.id, file_name)
                )
                skipped_exists += 1
                counter += 1
                continue

            if not self.needs_regeneration(file):
                missing_thumbs = self.get_missing_thumbnails(file)
                if not missing_thumbs:
                    print(
                        "(%d/%d) ID: %d -- Skipped -- All thumbnails exist for %s"
                        % (counter, num_instances, instance.id, file_name)
                    )
                    skipped_exists += 1
                    regen_tracker[file_name] = True
                    counter += 1
                    continue
                else:
                    print(
                        "(%d/%d) ID: %d -- Processing %s (missing: %s)"
                        % (counter, num_instances, instance.id, file_name, ", ".join(missing_thumbs))
                    )
            else:
                action = "Force regenerating" if self.force_regen else "Processing"
                print(
                    "(%d/%d) ID: %d -- %s %s"
                    % (counter, num_instances, instance.id, action, file_name)
                )

            try:
                fdat = file.read()
                file.close()
                del file.file
            except IOError:
                # File doesn't exist in storage
                print(
                    "(%d/%d) ID %d -- Error -- File missing in storage"
                    % (counter, num_instances, instance.id)
                )
                error_count += 1
                counter += 1
                continue

            try:
                file_contents = ContentFile(fdat)
            except ValueError:
                # This field has no file associated with it, skip it.
                print(
                    "(%d/%d) ID %d -- Skipped -- No file content"
                    % (counter, num_instances, instance.id)
                )
                skipped_no_file += 1
                counter += 1
                continue

            # Saving pumps it back through the thumbnailer, if this is a
            # ThumbnailField. If not, it's still pretty harmless.
            try:
                file.generate_thumbs(file_name, file_contents)
                processed_count += 1
            except IOError as e:
                print(
                    "(%d/%d) ID %d -- Error -- Image may be corrupt (%s)"
                    % (counter, num_instances, instance.id, str(e))
                )
                error_count += 1
                counter += 1
                continue

            regen_tracker[file_name] = True
            counter += 1

        print("\nREGENERATION SUMMARY:")
        print(f"\tTotal instances: {num_instances}")
        print(f"\tProcessed (regenerated): {processed_count}")
        print(f"\tSkipped (no file): {skipped_no_file}")
        print(f"\tSkipped (thumbnails exist): {skipped_exists}")
        print(f"\tErrors: {error_count}")

        if self.force_regen:
            print("\nNote: --force was used, all thumbnails were regenerated")
        else:
            print("\nNote: Only missing thumbnails were regenerated\n\tUse --force to regenerate all thumbnails")
