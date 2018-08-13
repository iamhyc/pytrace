all:install

install:
	chmod +x ./pytrace.py
	sudo cp ./pytrace.py /usr/bin/pytrace

clean:
	rm -f *.dat*