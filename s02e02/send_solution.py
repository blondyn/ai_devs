from common import submit, get_api_key, api_get
from endpoints import DATA_ELECTRICITY


def send_solution(solution, api_key):
  responses = []
  for r, row in enumerate(solution):
      for c, cell in enumerate(row):
          if cell["delta"] != 0:
              rotations = cell["delta"] // 90
              position = f"{r+1}x{c+1}"
              for i in range(abs(rotations)):
                print(f"Rotating {position} {rotations} times")
                response = submit(api_key=api_key, task="electricity", answer={"rotate": position})
                print(response)
                responses.append(response)

  return responses



def main():
    api_key = get_api_key()
    data = api_get(DATA_ELECTRICITY.format(api_key=api_key), "png")

    # print(send_solution(SOLUTION, api_key))


if __name__ == "__main__":
    main()
