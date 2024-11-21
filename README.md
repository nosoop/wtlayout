# `wtlayout`

Launches the [Windows Terminal][] with command windows specified in an XML file.  Allows for
designing complex layouts without the need to write long, brittle command lines by hand.

> [!WARNING]
> Commands invoked using `wtlayout` will inherit the environment variables of the process (last
> checked on version 1.21.2911.0).  This includes the virtual environment.
> 
> `wtlayout` will try to simulate deactivation of any virtual environment it is in when
> performing subprocess calls.

[Windows Terminal]: https://github.com/microsoft/terminal

## Usage

An example configuration is available at `layout.example.xml`.

```
wtlayout layout.example.xml
```

## License

Zero-Clause BSD.  Thanks, and have fun.
