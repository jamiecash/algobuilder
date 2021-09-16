import logging
from celery import shared_task
from feature import feature


@shared_task(name='calculate_feature', queue='feature')
def calculate_feature(feature_execution_id: int):
    """
    Executes the feature calculation for the specified feature execution
    :param feature_execution_id:
    :return:
    """
    from feature import models  # Imported when needed, due to circular dependency

    # Logger
    log = logging.getLogger(__name__)

    # Get the feature execution model class from its id
    feature_execution_model = models.FeatureExecution.objects.get(id=feature_execution_id)

    # Only continue if the execution and base feature are active
    if feature_execution_model.active and feature_execution_model.feature.active:
        # Get instance
        feature_impl = feature.FeatureImplementation.instance(feature_execution_model.feature.name)

        # Execute
        log.debug(f"Running FeatureExecution for {feature_execution_model}.")
        feature_impl.execute(feature_execution_model)
