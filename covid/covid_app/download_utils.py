import requests
import requests.exceptions as exceptions


def download_file(url, output_path=None):
    data = requests.get(url, timeout=10)
    data.raise_for_status()
    if data.status_code != 200:
        raise exceptions.ConnectionError()

    # This check doesn't work if the message body uses compression
    # headers = data.headers
    # content_length = headers.get('content-length')
    # if content_length is not None:
    #     content_length = int(content_length)
    #     if content_length != len(data.content):
    #         raise exceptions.ConnectionError()

    if output_path is None:
        return data
    else:
        with open(output_path, 'wb') as output_file:
            output_file.write(data.content)


def download(url, output_path=None):
    try:
        return download_file(url, output_path)
    except (exceptions.ConnectionError, exceptions.Timeout) as err:
        print(f"[Download exception] {str(err)}")
        print(f"Retrying url '{url}'...")
        return download_file(url, output_path)