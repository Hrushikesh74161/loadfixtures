<h1 align="center">Load Fixtures</h1>

_loadfixtures_ is a command for loading fixtures in django which is built on top of django's _loaddata_ command.

## Features

- Loads fixtures based on relations between models. You don't have to worry about the order of fixtures.
- Supports django's database routing.
- Dry run to see which fixtures will be loaded.
- Ability to load specific app(s) or model(s).
- Including all the features supported by django's _loaddata_ command.

## How it is done

Internally a structure/graph is built which is logically equivalent to a topologically sorted graph.

This graph is built using the information in models.\_meta.\_forward_fields_map which has all the forward fields of a model.

All models or sourced from apps.all_models, which also has the intermediate models created by django for many to many fields. So no need to worry about those.

Using this graph, _loadfixtures_ knows which models to load first, so that later models fixtures won't have problems with foreign key references.

## Installation and Usage

---

### Installation

---

- This is still in development, so not in the form of a package.
- Download the loadfixtures app which is in the core folder.
- Add this to your project and change the name attribute in apps.py file to loadfixtures.

### Usage

---

All fixtures should be labeled in the form %(app*label)*%(model_name)(\_number).

Ex: auth_user, inventory_product_1 etc

Fixtures for a model should be stored in fixtures/ folder in its app or in the folders mentioned in FIXTURE_DIRS setting. Because only in those folder search for fixtures is done.

You can directly run python manage.py loadfixtures, it will load fixtures of all models defined in your project, including models in third party packages(if models exist), and django.

<<<<<<< HEAD
Optionally we can only load fixtures belonging to a specific model(s) or a specif app(s). Use tags -m and -a respectively.
=======
Optionally we can only load fixtures belonging to a specific model(s) or a specific app(s). Use tags -m and -a respectively.
>>>>>>> 3770e7a (Updated readme to match changes done in previous commit)

To exclude a model(s) or/and app(s) use -e tag.

For help python manage.py loadfixtures -h

### Configuration

---

There is only one specific setting for this, also this is mostly not needed.

LOAD_FIXTURES = {
'ONETOONEORMANY': []
}

If you use any relation(only foreign keys or onetoone fields, no need to mention manytomany fields) fields that are not part of django, then those should be listed in ONETOONEORMANY setting.

Ex: TreeForeignKey from mptt models. Then

ONETOONEORMANY: ['mptt.models.TreeForeignKey']

### Example:

---

App: inventory

Models:

```python
class Category(MPTTModel):
    parent = TreeForeignKey("self")
    ...

class Product(models.Model):
    category = TreeManyToManyField(Category)
    ...

class ProductAttribute(models.Model):
    ...

class ProductType(models.Model):
    product_type_attributes = models.ManyToManyField(ProductAttribute)
    ...

class ProductAttributeValue(models.Model):
    product_attribute = models.ForeignKey(ProductAttribute)
    ...

class ProductVariant(models.Model):
    product_type = models.ForeignKey(ProductType)
    product = models.ForeignKey(Product)
    attribute_values = models.ManyToManyField(ProductAttributeValue)
    ...

class Media(models.Model):
    product_variant = models.ForeignKey(ProductVariant)
    ...

class Stock(models.Model):
    product_variant = models.OneToOneField(ProductVariant)
    ...

class ProductVariantAttributeValue(models.Model):
    product_variant = models.ForeignKey(ProductVariant)
    attribute_value = models.ForeignKey(ProductAttributeValue)
    ...

class ProductTypeAttribute(models.Model):
    product_attribute = models.ForeignKey(ProductAttribute)
    product_type = models.ForeignKey(ProductType)
    ...

```

App: auth

Models:

```python

class Permission:
    ...

class Group:
    permissions = models.ManyToManyField(Permission)
    ...

class User:
    groups = models.ManyToManyField(Group)
    user_permissions = models.ManyToManyField(Permission)
    ...

```

Order in which fixtures for models are loaded (in a level there is no order) when command is executed:

Every Model in a level depends on atleast one model in its below level.

### python manage.py loadfixtures

> Level : 0

- auth.Permission

- auth.User

- auth.Group

- inventory.Category

- inventory.Product

- inventory.ProductAttribute

- inventory.ProductType

> Level : 1

- auth.User_groups

- auth.User_user_permissions

- auth.Group_permissions

- inventory.Product_category

- inventory.ProductAttributeValue

- inventory.ProductVariant

- inventory.ProductTypeAttribute

> Level : 2

- inventory.Media

- inventory.Stock

- inventory.ProductVariantAttributeValue

### python manage.py -a auth -e auth.Permission

> Level: 0

- auth.User

- auth.Group

> Level: 1

- auth.User_user_permissions

- auth.User_groups

- auth.Group_permissions

### python manage.py -m auth.User

> Level: 0

- auth.User

### python manage.py -m inventory.Product -m inventory.Stock -m auth.User

> Level: 0

- auth.User

- inventory.Product

> Level: 1

- None

> Level: 2

- inventory.Stock
