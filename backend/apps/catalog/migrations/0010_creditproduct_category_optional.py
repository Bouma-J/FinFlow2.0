from django.db import migrations, models
import django.db.models.deletion


def restore_missing_product_categories(apps, schema_editor):
    """Restore a harmless category before reversing the nullable-field change."""
    alias = schema_editor.connection.alias
    CreditProduct = apps.get_model("catalog", "CreditProduct")
    ProductCategory = apps.get_model("catalog", "ProductCategory")

    for product in CreditProduct.objects.using(alias).filter(category__isnull=True).iterator():
        category, _ = ProductCategory.objects.using(alias).get_or_create(
            tenant_id=product.tenant_id,
            code="NON_CLASSE",
            defaults={"label": "Non classé"},
        )
        product.category_id = category.pk
        product.save(using=alias, update_fields=["category"])


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0009_cbsproductreference_creditproduct_cbs_credit_product_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="creditproduct",
            name="category",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="products",
                to="catalog.productcategory",
                verbose_name="famille",
            ),
        ),
        migrations.RunPython(migrations.RunPython.noop, restore_missing_product_categories),
    ]
