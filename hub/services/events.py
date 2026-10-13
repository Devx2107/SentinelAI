from database.queries.events_query import query_events


def list_events(providers, args):
    return query_events(providers.store, args)
