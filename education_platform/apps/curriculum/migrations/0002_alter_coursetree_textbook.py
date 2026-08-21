import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("curriculum", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="coursetree",
            name="textbook",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="course_trees",
                to="resources.textbook",
                verbose_name="对应教材",
            ),
        ),
    ]
