class ProductionDataRouter(object):
    using = 'production'
    app_label = 'production'

    def db_for_read(self, model, **hints):
        if model._meta.app_label == self.app_label:
            return self.using

    def db_for_write(self, model, **hints):
        if model._meta.app_label == self.app_label:
            return self.using

    def allow_syncdb(self, db, model):
        if model._meta.app_label == self.app_label:
            return db == self.using
        return False


class StagingDataRouter(object):
    using = 'staging'
    app_label = 'staging'

    def db_for_read(self, model, **hints):
        if model._meta.app_label == self.app_label:
            return self.using

    def db_for_write(self, model, **hints):
        if model._meta.app_label == self.app_label:
            return self.using

    def allow_syncdb(self, db, model):
        if model._meta.app_label == self.app_label:
            return db == self.using
        return False